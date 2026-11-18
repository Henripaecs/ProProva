"""
PASSO 3 — Lógica de correção: ROI (imagem) + AnswerGridSpec → respostas → nota.

Ideia central: medir o ESCURECIMENTO de cada bolha (0 = papel limpo, 1 = preto) dentro de um
disco interno (que evita o contorno impresso) e decidir por valores RELATIVOS ao "branco" da
própria folha, não por limiares absolutos. Assim, caneta forte, lápis fraco, sombra ou
papel amarelado se comportam de forma parecida.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import cv2
import numpy as np

from .layout import PPMM, AnswerGridSpec
from .preprocess import normalize_illumination


class MarkStatus(str, Enum):
    BLANK = "blank"          # nenhuma marca
    SINGLE = "single"        # uma marca clara
    MULTIPLE = "multiple"    # 2+ marcas concorrentes (rasura / dupla marcação)
    AMBIGUOUS = "ambiguous"  # só marcas fracas (lápis claro? borracha? sujeira?)


@dataclass(frozen=True)
class GraderConfig:
    min_delta_mark: float = 0.25      # escurecimento acima da linha de base p/ contar como "marcada"
    faint_delta: float = 0.12         # abaixo disso é ruído; entre faint e mark = marca fraca
    dominance_ratio: float = 0.55     # rival só vale se tiver ≥55% da força da melhor marca
    inner_radius_frac: float = 0.68   # disco de medição = 68% do raio (foge do contorno impresso)
    search_px: int = 3                # tolera pequeno erro de homografia (±3 px)
    baseline_percentile: float = 30.0 # a maioria das bolhas está vazia → percentil baixo = "papel"


@dataclass
class QuestionResult:
    number: int                       # 1-based
    status: MarkStatus
    fills: list[float]                # escurecimento bruto de cada alternativa
    marked: list[str]                 # letras acima do limiar "marcada"
    answer: str | None                # resposta final (None = branco / indecidida)
    confidence: float
    needs_review: bool = False        # True → o professor precisa confirmar no painel
    source: str = "omr"               # omr | human


# ───────────────────────────── medição ────────────────────────────────────────
def measure_fills(roi_bgr: np.ndarray, spec: AnswerGridSpec, cfg: GraderConfig = GraderConfig()) -> np.ndarray:
    """Matriz (n_questões × n_opções) com o escurecimento médio de cada bolha."""
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    flat = normalize_illumination(gray, feature_px=int(spec.bubble_diameter_mm * PPMM * 1.6))
    flat = cv2.GaussianBlur(flat, (3, 3), 0)
    dark = 1.0 - flat.astype(np.float32) / 255.0

    ri = max(2, int(spec.bubble_radius_px * cfg.inner_radius_frac))
    yy, xx = np.ogrid[-ri:ri + 1, -ri:ri + 1]
    disk = (xx ** 2 + yy ** 2) <= ri ** 2
    H, W = dark.shape
    s = cfg.search_px

    fills = np.zeros((spec.n_questions, spec.n_options), dtype=np.float32)
    for q in range(spec.n_questions):
        for o in range(spec.n_options):
            cx, cy = (int(round(v)) for v in spec.bubble_center_roi_px(q, o))
            # Mínimo sobre pequenos deslocamentos: se a grade estiver 2-3 px torta, o disco
            # tenderia a "tocar" o contorno impresso e inflar o valor de bolhas vazias.
            vals = []
            for dy in (-s, 0, s):
                for dx in (-s, 0, s):
                    y0, x0 = cy + dy - ri, cx + dx - ri
                    if y0 < 0 or x0 < 0 or y0 + 2 * ri + 1 > H or x0 + 2 * ri + 1 > W:
                        continue
                    vals.append(float(dark[y0:y0 + 2 * ri + 1, x0:x0 + 2 * ri + 1][disk].mean()))
            if not vals:
                raise ValueError(f"Bolha q={q + 1} op={o} fora da ROI — layout inconsistente.")
            fills[q, o] = min(vals)
    return fills


# ───────────────────────────── decisão ────────────────────────────────────────
def classify_question(number: int, row: np.ndarray, baseline: float,
                      spec: AnswerGridSpec, cfg: GraderConfig = GraderConfig()) -> QuestionResult:
    delta = row - baseline
    order = np.argsort(-delta)
    d1 = float(delta[order[0]])
    letters = spec.options
    marked = [letters[i] for i in range(len(row)) if delta[i] >= cfg.min_delta_mark]
    fills = [round(float(v), 4) for v in row]

    if d1 < cfg.faint_delta:
        return QuestionResult(number, MarkStatus.BLANK, fills, marked, None, 0.95)

    if d1 < cfg.min_delta_mark:     # só marcas fracas
        return QuestionResult(number, MarkStatus.AMBIGUOUS, fills, marked, None, 0.3, needs_review=True)

    # Rivais: outras bolhas com força comparável à melhor. Um resíduo de borracha costuma
    # ficar bem abaixo (< dominance_ratio) da marca definitiva → não conta como rival.
    rivals = [int(i) for i in order[1:] if delta[i] >= cfg.faint_delta and delta[i] / d1 >= cfg.dominance_ratio]
    if not rivals:
        second = float(delta[order[1]]) if len(order) > 1 else 0.0
        conf = float(np.clip(1.0 - max(second, 0.0) / d1, 0.0, 1.0))
        return QuestionResult(number, MarkStatus.SINGLE, fills, marked or [letters[order[0]]],
                              letters[order[0]], conf)

    return QuestionResult(number, MarkStatus.MULTIPLE, fills, marked, None, 0.0, needs_review=True)


def grade_roi(roi_bgr: np.ndarray, spec: AnswerGridSpec,
              cfg: GraderConfig = GraderConfig()) -> list[QuestionResult]:
    fills = measure_fills(roi_bgr, spec, cfg)
    baseline = float(np.percentile(fills, cfg.baseline_percentile))
    return [classify_question(q + 1, fills[q], baseline, spec, cfg) for q in range(spec.n_questions)]


# ───────────────────────────── revisão humana ─────────────────────────────────
def apply_human_review(result: QuestionResult, answer: str | None, spec: AnswerGridSpec) -> None:
    """Professor decide a questão: letra válida, ou None para 'em branco / sem resposta'."""
    if answer is not None:
        answer = answer.strip().upper()
        if answer not in spec.options:
            raise ValueError(f"Alternativa inválida: {answer!r}. Use uma de {spec.options} ou null.")
    result.answer = answer
    result.status = MarkStatus.BLANK if answer is None else MarkStatus.SINGLE
    result.needs_review, result.source, result.confidence = False, "human", 1.0


# ───────────────────────────── nota ───────────────────────────────────────────
@dataclass
class ExamScore:
    points: float = 0.0
    max_points: float = 0.0
    correct: int = 0
    wrong: int = 0
    blank: int = 0
    annulled: int = 0
    pending: int = 0                  # aguardam revisão do professor — nota é PARCIAL se > 0
    detail: dict[int, str] = field(default_factory=dict)


def score_exam(results: list[QuestionResult],
               answer_key: dict[int, str | list[str] | None],
               weights: dict[int, float] | None = None) -> ExamScore:
    """
    answer_key[n]: "B" | ["A","C"] (várias aceitas) | None (questão anulada → ponto para todos).
    """
    weights = weights or {}
    s = ExamScore()
    for r in results:
        key = answer_key.get(r.number)
        w = float(weights.get(r.number, 1.0))
        s.max_points += w
        if key is None:
            s.annulled += 1; s.points += w; s.detail[r.number] = "annulled"; continue
        if r.needs_review:
            s.pending += 1; s.detail[r.number] = "pending"; continue
        if r.answer is None:
            s.blank += 1; s.detail[r.number] = "blank"; continue
        accepted = {key} if isinstance(key, str) else set(key)
        if r.answer in accepted:
            s.correct += 1; s.points += w; s.detail[r.number] = "correct"
        else:
            s.wrong += 1; s.detail[r.number] = "wrong"
    return s


# ───────────────────────────── recorte p/ revisão ────────────────────────────────
def crop_question_row(roi_bgr: np.ndarray, spec: AnswerGridSpec, question_number: int,
                      upscale: int = 3) -> bytes:
    """
    PNG da LINHA da questão (rótulo + bolhas), ampliado e com as letras A..E desenhadas
    abaixo de cada bolha. É o que o professor vê no painel para decidir a questão.
    Nunca inclui nome do aluno nem QR.
    """
    q = question_number - 1
    x_first, y = spec.bubble_center_roi_px(q, 0)
    x_last, _ = spec.bubble_center_roi_px(q, spec.n_options - 1)
    half_h = spec.row_pitch_mm / 2 * PPMM
    x0 = int(max(0, x_first - (spec.label_width_mm + spec.bubble_diameter_mm) * PPMM * 0.9))
    x1 = int(min(roi_bgr.shape[1], x_last + (spec.bubble_diameter_mm + 1.5) * PPMM))
    y0, y1 = int(max(0, y - half_h)), int(min(roi_bgr.shape[0], y + half_h))
    crop = roi_bgr[y0:y1, x0:x1].copy()
    crop = cv2.resize(crop, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, 0, 44, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    for o, letter in enumerate(spec.options):
        cx, _ = spec.bubble_center_roi_px(q, o)
        px = int((cx - x0) * upscale) - 10
        cv2.putText(crop, letter, (px, crop.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
    ok, png = cv2.imencode(".png", crop)
    if not ok:
        raise RuntimeError("Falha ao codificar o recorte")
    return png.tobytes()
