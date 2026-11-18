"""
Teste sintético de ponta a ponta (sem câmera): desenha um cartão no espaço canônico,
simula uma foto ruim (perspectiva, rotação, sombra, ruído, desfoque) e confere se o pipeline
recupera as respostas. Rode:  cd backend && python ../tests/synthetic_roundtrip.py
"""
import sys, uuid
from pathlib import Path

import cv2
import numpy as np
import qrcode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.omr.grader import MarkStatus, grade_roi
from app.omr.layout import (CANVAS_H_PX, CANVAS_W_PX, FIDUCIAL_CENTERS_MM, MARKER_SIZE_MM, PPMM,
                            QR_ZONE_MM, AnswerGridSpec)
from app.omr.qr import SheetPayload, decode_payload, encode_payload
from app.omr.sheet_aligner import align_sheet

SECRET = b"teste"
rng = np.random.default_rng(7)


def draw_sheet(spec, qr_text, answers, faint=()):
    img = np.full((CANVAS_H_PX, CANVAS_W_PX, 3), 255, np.uint8)
    h = int(MARKER_SIZE_MM / 2 * PPMM)
    for cx, cy in FIDUCIAL_CENTERS_MM:
        cv2.rectangle(img, (int(cx * PPMM) - h, int(cy * PPMM) - h), (int(cx * PPMM) + h, int(cy * PPMM) + h), (0, 0, 0), -1)
    x, y, w, _ = QR_ZONE_MM
    qr = np.array(qrcode.make(qr_text, border=0).convert("RGB"))[:, :, ::-1]
    side = int((w - 6) * PPMM)
    img[int((y + 3) * PPMM):int((y + 3) * PPMM) + side, int((x + 3) * PPMM):int((x + 3) * PPMM) + side] = \
        cv2.resize(qr, (side, side), interpolation=cv2.INTER_NEAREST)
    r = int(spec.bubble_radius_px)
    for q in range(spec.n_questions):
        for o in range(spec.n_options):
            cx, cy = (int(v * PPMM) for v in spec.bubble_center_mm(q, o))
            cv2.circle(img, (cx, cy), r, (0, 0, 0), 2, cv2.LINE_AA)
            if answers.get(q + 1) and spec.options.index(answers[q + 1]) == o:
                cv2.circle(img, (cx, cy), int(r * 0.92), (70, 60, 50), -1, cv2.LINE_AA)
            if (q + 1, spec.options[o]) in faint:           # resíduo de borracha / rasura
                cv2.circle(img, (cx, cy), int(r * 0.85), (150, 150, 150), -1, cv2.LINE_AA)
    return img


def simulate_photo(sheet, rot90=0):
    H, W = 4000, 3000
    bg = np.full((H, W, 3), 70, np.uint8)
    src = np.float32([[0, 0], [CANVAS_W_PX, 0], [CANVAS_W_PX, CANVAS_H_PX], [0, CANVAS_H_PX]])
    dst = np.float32([[380, 520], [2650, 430], [2820, 3620], [260, 3720]]) + rng.normal(0, 15, (4, 2)).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(sheet, M, (W, H), dst=bg, borderMode=cv2.BORDER_TRANSPARENT)
    gx = np.linspace(0.45, 1.05, W, dtype=np.float32)[None, :, None]          # gradiente de luz forte
    gy = np.linspace(0.85, 1.0, H, dtype=np.float32)[:, None, None]
    photo = np.clip(photo.astype(np.float32) * gx * gy + rng.normal(0, 6, photo.shape), 0, 255).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (0, 0), 1.2)
    photo = cv2.resize(photo, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(np.rot90(photo, rot90))


def run(rot90):
    spec = AnswerGridSpec(n_questions=50, n_options=5, columns=4)
    truth = {q: spec.options[int(rng.integers(0, 5))] for q in range(1, 51)}
    truth[5] = None                                              # em branco
    faint = {(10, "A")}                                          # resíduo fraco, resposta forte = truth[10]
    truth[10] = "C" if truth[10] != "C" else "D"
    both = {20: ("B", "D")}                                      # dupla marcação real → MULTIPLE
    answers = dict(truth)
    qr_text = encode_payload(SheetPayload(uuid.uuid4(), uuid.uuid4(), 3), SECRET)
    sheet = draw_sheet(spec, qr_text, answers, faint)
    for o_letter in both[20]:                                    # força 2 marcas fortes na q20
        o = spec.options.index(o_letter); cx, cy = (int(v * PPMM) for v in spec.bubble_center_mm(19, o))
        cv2.circle(sheet, (cx, cy), int(spec.bubble_radius_px * .92), (70, 60, 50), -1, cv2.LINE_AA)
    photo = simulate_photo(sheet, rot90)

    aligned = align_sheet(photo)
    assert decode_payload(aligned.qr_text, SECRET).version == 3
    results = grade_roi(aligned.roi, spec)
    errors = []
    for r in results:
        if r.number == 20:
            if r.status != MarkStatus.MULTIPLE: errors.append((20, r.status.value))
        elif r.answer != truth[r.number]:
            errors.append((r.number, r.answer, truth[r.number], r.fills))
    print(f"rot90={rot90}  giro detectado={aligned.rotation_steps}  erros={len(errors)}", errors[:3])
    return not errors


if __name__ == "__main__":
    ok = all(run(k) for k in range(4))
    print("PASSOU" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
