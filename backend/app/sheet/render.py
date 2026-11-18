"""Gera o HTML/PDF do cartão-resposta a partir do AnswerGridSpec (mesma geometria do leitor)."""
from __future__ import annotations

import asyncio
import base64
import io
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import BACKEND_DIR
from app.omr.layout import (FIDUCIAL_CENTERS_MM, MARKER_SIZE_MM, QR_ZONE_MM, ROI_MM, AnswerGridSpec)
from app.omr.qr import SheetPayload, encode_payload

_TEMPLATES = Path(__file__).resolve().parents[3] / "answer_sheet"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def make_qr_png_b64(text: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=12, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def render_answer_sheet_html(spec: AnswerGridSpec, *, exam_id: UUID, student_id: UUID, version: int,
                             exam_title: str, student_name: str, class_name: str, qr_secret: bytes) -> str:
    qr_text = encode_payload(SheetPayload(exam_id, student_id, version), qr_secret)
    d = spec.bubble_diameter_mm
    bubbles, labels, headers = [], [], []
    for q in range(spec.n_questions):
        for o in range(spec.n_options):
            cx, cy = spec.bubble_center_mm(q, o)
            bubbles.append({"left": round(cx - d / 2, 3), "top": round(cy - d / 2, 3)})
        _, cy = spec.bubble_center_mm(q, 0)
        labels.append({"left": round(spec.column_origin_mm(q), 3), "top": round(cy - d / 2, 3),
                       "text": f"{q + 1:02d}"})
    for c in range(spec.columns):                       # letras A..E no topo de cada coluna
        q0 = c * spec.rows_per_col
        if q0 >= spec.n_questions:
            break
        for o, letter in enumerate(spec.options):
            cx, _ = spec.bubble_center_mm(q0, o)
            headers.append({"left": round(cx - d / 2, 3), "top": ROI_MM[1] + 0.8, "letter": letter})
    half = MARKER_SIZE_MM / 2
    return _env.get_template("answer_sheet.html.j2").render(
        marker_mm=MARKER_SIZE_MM, markers=[(round(x - half, 3), round(y - half, 3)) for x, y in FIDUCIAL_CENTERS_MM],
        qr=QR_ZONE_MM, qr_png_b64=make_qr_png_b64(qr_text), d=d, label_w=spec.label_width_mm - 2,
        exam_title=exam_title, student_name=student_name, class_name=class_name,
        bubbles=bubbles, labels=labels, option_headers=headers)


class PdfRenderError(RuntimeError):
    pass


def render_pdf_sync(html: str, timeout_s: int = 90) -> bytes:
    """HTML → PDF com Chromium headless (mesmo motor em qualquer máquina → geometria idêntica)."""
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / "sheet.html", Path(d) / "sheet.pdf"
        src.write_text(html, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-m", "app.sheet.pdf_worker", str(src), str(out)],
                                  cwd=BACKEND_DIR, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise PdfRenderError("Tempo esgotado ao gerar o PDF") from exc
        if proc.returncode != 0 or not out.exists():
            raise PdfRenderError(proc.stderr.strip()[-600:] or "Falha ao gerar o PDF")
        return out.read_bytes()


async def render_pdf(html: str) -> bytes:
    return await asyncio.to_thread(render_pdf_sync, html)
