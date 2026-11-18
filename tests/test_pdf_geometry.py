"""
Autoteste da geometria do PDF REAL (HTML → Chromium → PDF): rasteriza e confere
  1) o PDF tem 1 página;  2) os 4 marcadores estão onde layout.py diz;
  3) os contornos das bolhas estão onde o leitor vai medir;  4) o pipeline completo lê o QR.
Rode: cd backend && python ../tests/test_pdf_geometry.py
"""
import sys, uuid
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config
from app.omr.grader import MarkStatus, grade_roi
from app.omr.layout import CANVAS_H_PX, CANVAS_W_PX, FIDUCIAL_CENTERS_MM, PPMM, AnswerGridSpec
from app.omr.sheet_aligner import align_sheet
from app.sheet.render import render_answer_sheet_html, render_pdf_sync
from synthetic_roundtrip import simulate_photo

spec = AnswerGridSpec(50)
html = render_answer_sheet_html(spec, exam_id=uuid.uuid4(), student_id=uuid.uuid4(), version=1, exam_title="Prova",
                                student_name="Maria Silva", class_name="9A", qr_secret=config.QR_SECRET)
pdf = pdfium.PdfDocument(render_pdf_sync(html))
assert len(pdf) == 1, f"PDF com {len(pdf)} páginas (conteúdo vazou da folha A4)"
scale = PPMM / (72 / 25.4)                                   # pt → 8 px/mm
img = np.array(pdf[0].render(scale=scale).to_pil().convert("RGB"))[:, :, ::-1]
img = cv2.resize(img, (CANVAS_W_PX, CANVAS_H_PX), interpolation=cv2.INTER_AREA)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
print("1 página ok;", img.shape[1], "x", img.shape[0], "px")

# 2) marcadores: centroide de cada quadrado preto vs. posição teórica
for cx, cy in FIDUCIAL_CENTERS_MM:
    x0, y0, r = int(cx * PPMM), int(cy * PPMM), int(8 * PPMM)
    win = (gray[y0 - r:y0 + r, x0 - r:x0 + r] < 128).astype(np.uint8)
    m = cv2.moments(win, binaryImage=True)
    dx, dy = m["m10"] / m["m00"] - r, m["m01"] / m["m00"] - r
    print(f"marcador ({cx:.0f},{cy:.0f}) mm: deslocamento dx={dx:+.2f} dy={dy:+.2f} px")
    assert np.hypot(dx, dy) < 2.0          # a homografia + busca ±3 px do leitor absorvem isso

# 3) contornos das bolhas: em cada direção deve haver traço escuro na faixa [raio-4, raio+1] px
#    e o interior (disco de medição do leitor) deve estar limpo
rr = spec.bubble_radius_px
ri = int(rr * 0.68)
yy, xx = np.ogrid[-ri:ri + 1, -ri:ri + 1]
disk = (xx ** 2 + yy ** 2) <= ri ** 2
bad = 0
for q in range(spec.n_questions):
    for o in range(spec.n_options):
        cx, cy = (int(round(v * PPMM)) for v in spec.bubble_center_mm(q, o))
        hits = 0
        for a in np.linspace(0, 2 * np.pi, 16, endpoint=False):
            samples = [gray[int(round(cy + k * np.sin(a))), int(round(cx + k * np.cos(a)))] for k in np.arange(rr - 4, rr + 1.5, 0.5)]
            hits += min(samples) < 110
        interior = gray[cy - ri:cy + ri + 1, cx - ri:cx + ri + 1][disk].mean()
        if hits < 15 or interior < 235:
            bad += 1
print(f"bolhas com anel fora do previsto: {bad}/250")
assert bad == 0

# 4) pipeline completo em cima do PDF real (foto simulada)
aligned = align_sheet(simulate_photo(img))
res = grade_roi(aligned.roi, spec)
assert all(r.status == MarkStatus.BLANK for r in res), "cartão vazio deveria ser lido como todo em branco"
print("pipeline lê o QR do PDF e as 50 questões vazias → todas BLANK")
print("PDF OK")
