"""
Prova completa: caderno (estilo livre) + cartão-resposta (geometria fixa) → PDF por aluno / por turma.

O caderno e o cartão são renderizados como documentos separados e só depois unidos (pypdf).
Isso garante que fonte, colunas e imagens escolhidas no editor nunca desloquem uma bolha.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter

from app.config import BACKEND_DIR
from app.exam_content import FONT_STACKS, ExamContent, StyleIn, rich
from app.omr.layout import AnswerGridSpec
from app.sheet.render import PdfRenderError, render_answer_sheet_html

_TEMPLATES = Path(__file__).resolve().parents[3] / "answer_sheet"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
_env.filters["rich"] = rich


@dataclass
class StudentRef:
    id: UUID
    name: str
    enrollment: str | None = None


@dataclass
class PrintJob:
    exam_id: UUID
    version: int
    title: str
    class_name: str
    spec: AnswerGridSpec
    content: ExamContent | None            # None → prova só com cartão (sem caderno)
    style: StyleIn
    assets: dict[str, tuple[str, bytes]]   # asset_id → (mime, bytes)


def _fmt_points(w: float) -> str:
    txt = f"{w:.1f}".replace(".", ",")
    return f"{txt} pt" if w == 1 else f"{txt} pts"


def render_booklet_html(job: PrintJob, student_name: str | None = None) -> str:
    if job.content is None:
        raise ValueError("Esta prova não tem caderno (foi criada só com gabarito).")
    def src(asset_id: str | None) -> str | None:
        if not asset_id or asset_id not in job.assets:
            return None
        mime, raw = job.assets[asset_id]
        return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    questions = []
    for q in job.content.questions:
        questions.append({"stem": q.stem, "image_src": src(q.image), "image_width": q.image_width,
                          "points": _fmt_points(q.weight),
                          "options": [{"text": t, "image_src": src(img)} for t, img in zip(q.options, q.option_images)],
                          "option_image_height": q.option_image_height,
                          "section": q.section.strip(), "section_text": q.section_text.strip()})
    h = job.content.header
    logo_src = src(h.logo) if h.show_logo else None
    return _env.get_template("exam_booklet.html.j2").render(
        title=job.title, header=h, style=job.style, logo_src=logo_src,
        font_stack=FONT_STACKS[job.style.font_family], questions=questions,
        student_name=student_name, class_name=job.class_name)


def _sheet_html(job: PrintJob, student: StudentRef, qr_secret: bytes) -> str:
    return render_answer_sheet_html(job.spec, exam_id=job.exam_id, student_id=student.id, version=job.version,
                                    exam_title=job.title, student_name=student.name,
                                    class_name=job.class_name, qr_secret=qr_secret)


def _run_jobs(jobs: list[dict], tmp: Path, timeout_s: int) -> None:
    jf = tmp / "jobs.json"
    jf.write_text(json.dumps(jobs), encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, "-m", "app.sheet.pdf_worker", "--jobs", str(jf)],
                              cwd=BACKEND_DIR, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise PdfRenderError("Tempo esgotado ao gerar os PDFs") from exc
    if proc.returncode != 0 or not all(Path(j["pdf"]).exists() for j in jobs):
        raise PdfRenderError(proc.stderr.strip()[-600:] or "Falha ao gerar os PDFs")


def safe_filename(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\- ]+", "", text).strip().replace(" ", "_")
    return (text or "arquivo")[:max_len]


def render_bundle_sync(job: PrintJob, students: list[StudentRef], qr_secret: bytes, *,
                       include_booklet: bool = True, personalize: bool = True, duplex: bool = False,
                       layout: str = "single") -> tuple[bytes, str]:
    """
    Gera a prova de cada aluno: [caderno] + cartão-resposta (sempre por último, para destacar).
      include_booklet=False → só cartões;  personalize → nome do aluno no cabeçalho do caderno
      duplex=True → insere página em branco para o cartão começar numa folha nova (frente e verso)
      layout="single" → um PDF com a turma inteira;  "zip" → um PDF por aluno dentro de um ZIP
    Retorna (bytes, media_type).
    """
    if not students:
        raise ValueError("A turma não tem alunos.")
    include_booklet = include_booklet and job.content is not None
    timeout = 60 + 6 * len(students) * (2 if include_booklet else 1)
    footer = f"{job.title} — {job.class_name}"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        jobs: list[dict] = []
        booklet_pdf: dict[UUID | None, str] = {}

        def add(html: str, name: str, kind: str) -> str:
            src, out = tmp / f"{name}.html", tmp / f"{name}.pdf"
            src.write_text(html, encoding="utf-8")
            jobs.append({"html": str(src), "pdf": str(out), "kind": kind, "footer": footer})
            return str(out)

        if include_booklet and not personalize:
            booklet_pdf[None] = add(render_booklet_html(job), "booklet", "booklet")
        sheet_pdf = {}
        for i, s in enumerate(students):
            if include_booklet and personalize:
                booklet_pdf[s.id] = add(render_booklet_html(job, s.name), f"b{i}", "booklet")
            sheet_pdf[s.id] = add(_sheet_html(job, s, qr_secret), f"s{i}", "sheet")
        _run_jobs(jobs, tmp, timeout)

        def student_writer(s: StudentRef, w: PdfWriter) -> None:
            if include_booklet:
                pages = PdfReader(booklet_pdf[s.id if personalize else None]).pages
                for p in pages:
                    w.add_page(p)
                if duplex and len(pages) % 2:
                    w.add_blank_page(width=pages[0].mediabox.width, height=pages[0].mediabox.height)
            w.add_page(PdfReader(sheet_pdf[s.id]).pages[0])
            if duplex:                     # o verso do cartão fica em branco → próximo aluno em folha nova
                ref = w.pages[-1]
                w.add_blank_page(width=ref.mediabox.width, height=ref.mediabox.height)

        if layout == "zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, s in enumerate(students, 1):
                    w = PdfWriter()
                    student_writer(s, w)
                    out = io.BytesIO()
                    w.write(out)
                    zf.writestr(f"{i:02d}_{safe_filename(s.name)}.pdf", out.getvalue())
            return buf.getvalue(), "application/zip"

        w = PdfWriter()
        for s in students:
            student_writer(s, w)
        out = io.BytesIO()
        w.write(out)
        return out.getvalue(), "application/pdf"


def render_booklet_pdf_sync(job: PrintJob) -> bytes:
    """Pré-visualização do caderno (sem aluno) — usada pelo editor."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src, out = tmp / "b.html", tmp / "b.pdf"
        src.write_text(render_booklet_html(job), encoding="utf-8")
        jobs = [{"html": str(src), "pdf": str(out), "kind": "booklet", "footer": job.title}]
        _run_jobs(jobs, tmp, 90)
        return out.read_bytes()


async def render_bundle(*args, **kwargs) -> tuple[bytes, str]:
    return await asyncio.to_thread(render_bundle_sync, *args, **kwargs)


async def render_booklet_pdf(job: PrintJob) -> bytes:
    return await asyncio.to_thread(render_booklet_pdf_sync, job)
