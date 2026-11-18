"""
Geometria do cartão-resposta — FONTE ÚNICA DA VERDADE.

Este módulo é importado tanto pelo renderizador (HTML/PDF) quanto pelo motor de
visão computacional. Como os dois leem as mesmas constantes, é impossível o
cartão impresso e o leitor "discordarem" sobre onde estão as bolhas.

Todas as medidas físicas estão em milímetros. A imagem "canônica" (resultado da
homografia) usa PPMM pixels por mm.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

import numpy as np

# ── Página (A4 retrato) ───────────────────────────────────────────────────────
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
PPMM = 8                                   # px/mm da imagem canônica (1680x2376)
CANVAS_W_PX = round(PAGE_W_MM * PPMM)
CANVAS_H_PX = round(PAGE_H_MM * PPMM)

# ── Marcadores fiduciais (quadrados pretos sólidos nos 4 cantos) ──────────────
MARKER_SIZE_MM = 10.0
MARKER_MARGIN_MM = 8.0                     # distância da borda da folha
_C = MARKER_MARGIN_MM + MARKER_SIZE_MM / 2
# Ordem: TL, TR, BR, BL (sentido horário). São os pontos-destino da homografia.
FIDUCIAL_CENTERS_MM = (
    (_C, _C),
    (PAGE_W_MM - _C, _C),
    (PAGE_W_MM - _C, PAGE_H_MM - _C),
    (_C, PAGE_H_MM - _C),
)

# ── Zonas reservadas (x, y, w, h) em mm ───────────────────────────────────────
QR_ZONE_MM = (156.0, 12.0, 34.0, 34.0)     # inclui "quiet zone" branca de 3 mm
ROI_MM = (20.0, 52.0, 170.0, 224.0)        # área das bolhas (recorte do Passo 2)
HEADER_H_MM = 6.0                          # faixa com as letras A B C D E


def fiducial_centers_px() -> np.ndarray:
    return np.array(FIDUCIAL_CENTERS_MM, dtype=np.float32) * PPMM


def roi_slices_px() -> tuple[slice, slice]:
    x, y, w, h = ROI_MM
    return (slice(round(y * PPMM), round((y + h) * PPMM)),
            slice(round(x * PPMM), round((x + w) * PPMM)))


def qr_zone_slices_px() -> tuple[slice, slice]:
    x, y, w, h = QR_ZONE_MM
    return (slice(round(y * PPMM), round((y + h) * PPMM)),
            slice(round(x * PPMM), round((x + w) * PPMM)))


# ── Grade de respostas (varia por prova; é salva no banco por versão) ─────────
@dataclass(frozen=True)
class AnswerGridSpec:
    n_questions: int
    n_options: int = 5
    columns: int = 4
    bubble_diameter_mm: float = 4.6
    option_pitch_mm: float = 6.2
    row_pitch_mm: float = 7.4
    label_width_mm: float = 9.0

    def __post_init__(self) -> None:
        roi_w, roi_h = ROI_MM[2], ROI_MM[3]
        if not (1 <= self.n_options <= 6):
            raise ValueError("n_options deve estar entre 1 e 6")
        need_w = (self.label_width_mm + (self.n_options - 1) * self.option_pitch_mm
                  + self.bubble_diameter_mm + 2.0)
        if need_w > roi_w / self.columns:
            raise ValueError(f"Coluna estreita demais ({need_w:.1f} mm > {roi_w/self.columns:.1f} mm)")
        if HEADER_H_MM + self.rows_per_col * self.row_pitch_mm > roi_h:
            raise ValueError("Questões demais para uma folha; use mais colunas ou 2 cartões")

    # -- derivados -------------------------------------------------------------
    @property
    def rows_per_col(self) -> int:
        return math.ceil(self.n_questions / self.columns)

    @property
    def options(self) -> str:
        return "ABCDEF"[: self.n_options]

    @property
    def column_width_mm(self) -> float:
        return ROI_MM[2] / self.columns

    @property
    def bubble_radius_px(self) -> float:
        return self.bubble_diameter_mm / 2 * PPMM

    def column_origin_mm(self, q: int) -> float:
        """x (mm, página) do início da coluna da questão q (0-based)."""
        return ROI_MM[0] + (q // self.rows_per_col) * self.column_width_mm + 2.0

    def bubble_center_mm(self, q: int, o: int) -> tuple[float, float]:
        row = q % self.rows_per_col
        x = (self.column_origin_mm(q) + self.label_width_mm
             + self.bubble_diameter_mm / 2 + o * self.option_pitch_mm)
        y = ROI_MM[1] + HEADER_H_MM + row * self.row_pitch_mm + self.row_pitch_mm / 2
        return x, y

    def bubble_center_roi_px(self, q: int, o: int) -> tuple[float, float]:
        x, y = self.bubble_center_mm(q, o)
        return (x - ROI_MM[0]) * PPMM, (y - ROI_MM[1]) * PPMM

    # -- (de)serialização para o banco ----------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str | dict) -> "AnswerGridSpec":
        return cls(**(json.loads(raw) if isinstance(raw, str) else raw))
