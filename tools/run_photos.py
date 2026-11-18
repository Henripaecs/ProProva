"""
Roda o motor OMR numa pasta de fotos (sem servidor/banco) para validar e calibrar com papel real.

  python tools/run_photos.py fotos/ --gabarito samples/gabarito_teste.json
  python tools/run_photos.py fotos/ --questions 30 --columns 3

Por foto imprime: falha (com dica) OU resumo por status e acerto contra o gabarito.
Grava em ./debug:  <foto>_roi.jpg  (bolhas coloridas por status)  e  <foto>_fills.csv  (valores p/ calibrar limiares)
  verde = resposta única | vermelho = múltipla | amarelo = ambígua | cinza = em branco
"""
import argparse, csv, json, sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config
from app.omr.errors import OMRError
from app.omr.grader import GraderConfig, MarkStatus, classify_question, measure_fills
from app.omr.layout import AnswerGridSpec
from app.omr.qr import decode_payload
from app.omr.sheet_aligner import align_sheet

COLORS = {MarkStatus.SINGLE: (0, 170, 0), MarkStatus.MULTIPLE: (0, 0, 230),
          MarkStatus.AMBIGUOUS: (0, 200, 240), MarkStatus.BLANK: (150, 150, 150)}
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def process(path: Path, spec: AnswerGridSpec, cfg: GraderConfig, expected: dict | None, out: Path) -> bool:
    bgr = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)     # aceita acentos no Windows
    if bgr is None:
        print(f"[FALHA] {path.name}: não é uma imagem válida"); return False
    try:
        aligned = align_sheet(bgr)
    except OMRError as exc:
        print(f"[FALHA] {path.name}: {exc.code} — {exc.hint}"); return False
    try:
        decode_payload(aligned.qr_text, config.QR_SECRET)
        qr_ok = "QR ok"
    except OMRError:
        qr_ok = "QR lido mas assinatura NÃO confere (QR_SECRET diferente do usado na geração?)"

    fills = measure_fills(aligned.roi, spec, cfg)
    baseline = float(np.percentile(fills, cfg.baseline_percentile))
    results = [classify_question(q + 1, fills[q], baseline, spec, cfg) for q in range(spec.n_questions)]

    counts = {s: sum(r.status == s for r in results) for s in MarkStatus}
    print(f"[OK] {path.name}: giro={aligned.rotation_steps} {qr_ok} | baseline={baseline:.3f} | "
          + " ".join(f"{s.value}={n}" for s, n in counts.items()))

    if expected:
        ans, review = expected["answers"], set(expected.get("expect_review", []))
        wrong = []
        for r in results:
            if r.number in review:
                if not r.needs_review: wrong.append(f"q{r.number}: deveria ir p/ revisão, veio {r.status.value}")
            elif r.needs_review: wrong.append(f"q{r.number}: foi p/ revisão ({r.status.value}) mas era {ans[str(r.number)]}")
            elif r.answer != ans[str(r.number)]: wrong.append(f"q{r.number}: leu {r.answer}, esperado {ans[str(r.number)]}")
        print(f"     acertos {spec.n_questions - len(wrong)}/{spec.n_questions}" + ("" if not wrong else "  ↓"))
        for w in wrong[:15]: print("       -", w)

    img = aligned.roi.copy()
    for r in results:
        for o in range(spec.n_options):
            cx, cy = (int(v) for v in spec.bubble_center_roi_px(r.number - 1, o))
            chosen = r.answer == spec.options[o] or spec.options[o] in r.marked
            cv2.circle(img, (cx, cy), int(spec.bubble_radius_px) + (3 if chosen else 1),
                       COLORS[r.status], 3 if chosen else 1, cv2.LINE_AA)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", img)[1].tofile(str(out / f"{path.stem}_roi.jpg"))
    with open(out / f"{path.stem}_fills.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["questao", *spec.options, "status", "resposta"])
        for r in results: w.writerow([r.number, *r.fills, r.status.value, r.answer or ""])
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--questions", type=int, default=50)
    ap.add_argument("--options", type=int, default=5)
    ap.add_argument("--columns", type=int, default=4)
    ap.add_argument("--gabarito", help="JSON gerado por make_sample_sheet.py")
    ap.add_argument("--out", default="debug")
    a = ap.parse_args()
    spec = AnswerGridSpec(a.questions, a.options, a.columns)
    expected = json.loads(Path(a.gabarito).read_text(encoding="utf-8")) if a.gabarito else None
    files = sorted(p for p in Path(a.pasta).iterdir() if p.suffix.lower() in EXTS)
    if not files:
        sys.exit(f"Nenhuma imagem em {a.pasta}")
    ok = sum(process(p, spec, GraderConfig(), expected, Path(a.out)) for p in files)
    print(f"\n{ok}/{len(files)} fotos processadas. Veja a pasta '{a.out}/'.")


if __name__ == "__main__":
    main()
