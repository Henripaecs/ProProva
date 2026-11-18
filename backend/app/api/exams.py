"""
Provas: editor (conteúdo + estilo), imagens das questões, pré-visualização e impressão.

  POST   /v1/exams                               cria (com `content` do editor OU só `answer_key`)
  GET    /v1/exams                               lista
  GET    /v1/exams/{id}                          versão atual completa (para o editor)
  PUT    /v1/exams/{id}                          salva; se a versão já foi impressa → cria a próxima
  DELETE /v1/exams/{id}
  POST   /v1/exams/{id}/assets                   envia imagem (PNG/JPEG/WebP) → {"id": ...}
  GET    /v1/exams/{id}/assets/{asset_id}
  GET    /v1/exams/{id}/booklet?format=pdf|html  pré-visualização do caderno (sem aluno)
  GET    /v1/exams/{id}/sheets/{student_id}      só o cartão de um aluno
  GET    /v1/exams/{id}/students/{student_id}/print   caderno + cartão de um aluno (PDF)
  GET    /v1/exams/{id}/classes/{class_id}/print      turma inteira: PDF único ou ZIP (um PDF por aluno)
  GET    /v1/exams/{id}/results.csv              notas para planilha
"""
from __future__ import annotations

import csv
import io
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field, model_validator

from app import config
from app.api.scan import get_repo
from app.exam_content import ExamContent, StyleIn, asset_ids, derive_grid
from app.omr.grader import score_exam
from app.omr.layout import AnswerGridSpec
from app.security import current_teacher_id
from app.sheet.bundle import (PrintJob, StudentRef, render_booklet_html, render_booklet_pdf, render_bundle,
                              safe_filename)
from app.sheet.render import PdfRenderError, render_answer_sheet_html, render_pdf

router = APIRouter(prefix="/exams", tags=["provas"])

MAX_ASSET_BYTES = 5 * 1024 * 1024
MAX_ASSET_SIDE = 1800                  # px; reduz fotos enormes (o PDF fica leve)
PDF_HINT = "Rode: python -m playwright install chromium (ou use ?format=html). Detalhe: "


class ExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    columns: int = Field(4, ge=1, le=6)                   # colunas do CARTÃO-RESPOSTA
    # Forma 1 — editor completo: o gabarito sai do conteúdo
    content: ExamContent | None = None
    style: StyleIn = StyleIn()
    # Forma 2 — só cartão-resposta (prova impressa por fora)
    n_questions: int | None = Field(None, ge=1, le=120)
    n_options: int = Field(5, ge=2, le=6)
    answer_key: dict[int, str | list[str] | None] | None = None
    weights: dict[int, float] | None = None

    @model_validator(mode="after")
    def _one_form(self) -> "ExamIn":
        if self.content is None and (self.n_questions is None or self.answer_key is None):
            raise ValueError("Envie `content` (editor) ou `n_questions` + `answer_key` (só cartão).")
        return self


def _fit_spec(n_q: int, n_opt: int, columns: int) -> AnswerGridSpec:
    """Usa as colunas pedidas; se não couber, tenta outras (o professor não precisa saber de mm)."""
    last: ValueError | None = None
    for cols in [columns] + [c for c in range(1, 7) if c != columns]:
        try:
            return AnswerGridSpec(n_q, n_opt, cols)
        except ValueError as exc:
            last = exc if cols == columns else last
    raise HTTPException(422, f"Não cabe num cartão: {n_q} questões × {n_opt} alternativas ({last})")


def _build(body: ExamIn):
    if body.content is not None:
        n_q, n_opt, key, weights = derive_grid(body.content)
        content, style = body.content.model_dump(), body.style.model_dump()
    else:
        n_q, n_opt, key, weights = body.n_questions, body.n_options, body.answer_key, body.weights
        content, style = None, None
        spec_opts = "ABCDEF"[:n_opt]
        missing = set(range(1, n_q + 1)) - set(key)
        if missing:
            raise HTTPException(422, f"Gabarito sem as questões: {sorted(missing)[:10]}")
        for n, k in key.items():
            letters = [] if k is None else ([k] if isinstance(k, str) else k)
            if not 1 <= n <= n_q or any(l not in spec_opts for l in letters):
                raise HTTPException(422, f"Gabarito inválido na questão {n} (use letras de {spec_opts})")
    return _fit_spec(n_q, n_opt, body.columns), key, weights, content, style


# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_exam(body: ExamIn, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    if body.content is not None and asset_ids(body.content):
        raise HTTPException(422, "Crie a prova antes de anexar imagens (POST /exams/{id}/assets) e depois salve.")
    spec, key, weights, content, style = _build(body)
    eid = await repo.create_exam(tid, body.title, spec, key, weights, content, style)
    return {"id": str(eid), "version": 1, "columns": spec.columns}


@router.get("")
async def list_exams(repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    return await repo.list_exams(tid)


async def _exam_or_404(repo, tid: UUID, exam_id: UUID) -> dict:
    exam = await repo.get_exam(tid, exam_id)
    if exam is None:
        raise HTTPException(404, "Prova não encontrada")
    return exam


@router.get("/{exam_id}")
async def get_exam(exam_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    return await _exam_or_404(repo, tid, exam_id)


@router.put("/{exam_id}")
async def update_exam(exam_id: UUID, body: ExamIn, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    await _exam_or_404(repo, tid, exam_id)
    if body.content is not None:
        wanted = asset_ids(body.content)
        found = await repo.load_assets(exam_id, wanted)
        if wanted - set(found):
            raise HTTPException(422, f"Imagem não encontrada nesta prova: {sorted(wanted - set(found))[0]}")
    spec, key, weights, content, style = _build(body)
    res = await repo.update_exam(tid, exam_id, body.title, spec, key, weights, content, style)
    return {**res, "columns": spec.columns}


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(exam_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    files = await repo.delete_exam(tid, exam_id)
    if files is None:
        raise HTTPException(404, "Prova não encontrada")
    for f in files:
        Path(f).unlink(missing_ok=True)


# ── imagens ───────────────────────────────────────────────────────────────────
@router.post("/{exam_id}/assets", status_code=201)
async def upload_asset(exam_id: UUID, file: UploadFile = File(...), repo=Depends(get_repo),
                       tid: UUID = Depends(current_teacher_id)):
    raw = await file.read()
    if len(raw) > MAX_ASSET_BYTES:
        raise HTTPException(413, "Imagem grande demais (máx. 5 MB)")
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise HTTPException(422, "Arquivo não é uma imagem PNG/JPEG/WebP válida")
    # Reencoda sempre: valida o arquivo, remove metadados (EXIF/GPS) e limita o tamanho.
    scale = MAX_ASSET_SIDE / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    has_alpha = img.ndim == 3 and img.shape[2] == 4
    if has_alpha or (file.content_type or "").endswith("png"):
        ok, enc, mime, ext = *cv2.imencode(".png", img), "image/png", "png"
    else:
        ok, enc, mime, ext = *cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88]), "image/jpeg", "jpg"
    if not ok:
        raise HTTPException(422, "Não foi possível processar a imagem")
    aid = await repo.add_asset(tid, exam_id, mime, enc.tobytes(), ext)
    if aid is None:
        raise HTTPException(404, "Prova não encontrada")
    return {"id": str(aid), "width": int(img.shape[1]), "height": int(img.shape[0])}


@router.get("/{exam_id}/assets/{asset_id}")
async def get_asset(exam_id: UUID, asset_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    found = await repo.get_asset(tid, exam_id, asset_id)
    if not found or not Path(found[1]).exists():
        raise HTTPException(404, "Imagem não encontrada")
    return FileResponse(found[1], media_type=found[0])


# ── impressão ─────────────────────────────────────────────────────────────────
async def _print_job(repo, tid: UUID, exam_id: UUID, class_name: str = "") -> PrintJob:
    exam = await _exam_or_404(repo, tid, exam_id)
    content = ExamContent(**exam["content"]) if exam["content"] else None
    style = StyleIn(**(exam["style"] or {}))
    assets = await repo.load_assets(exam_id, asset_ids(content)) if content else {}
    return PrintJob(exam_id, exam["version"], exam["title"], class_name,
                    AnswerGridSpec.from_json(exam["grid_spec"]), content, style, assets)


@router.get("/{exam_id}/booklet")
async def booklet_preview(exam_id: UUID, format: str = Query("pdf", pattern="^(pdf|html)$"),
                          repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    job = await _print_job(repo, tid, exam_id)
    if job.content is None:
        raise HTTPException(409, "Esta prova foi criada só com gabarito; não há caderno para mostrar.")
    if format == "html":
        return HTMLResponse(render_booklet_html(job))
    try:
        pdf = await render_booklet_pdf(job)
    except PdfRenderError as exc:
        raise HTTPException(503, "Não foi possível gerar o PDF. " + PDF_HINT + str(exc)) from exc
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{safe_filename(job.title)}.pdf"'})


@router.get("/{exam_id}/sheets/{student_id}")
async def answer_sheet(exam_id: UUID, student_id: UUID, format: str = Query("pdf", pattern="^(pdf|html)$"),
                       repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    info = await repo.get_sheet_info(tid, exam_id, student_id)
    if info is None:
        raise HTTPException(404, "Prova ou aluno não encontrado")
    html = render_answer_sheet_html(info["spec"], exam_id=exam_id, student_id=student_id, version=info["version"],
                                    exam_title=info["title"], student_name=info["student_name"],
                                    class_name=info["class_name"], qr_secret=config.QR_SECRET)
    if format == "html":
        return HTMLResponse(html)
    try:
        pdf = await render_pdf(html)
    except PdfRenderError as exc:
        raise HTTPException(503, "Não foi possível gerar o PDF. " + PDF_HINT + str(exc)) from exc
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="cartao-{student_id}.pdf"'})


async def _render_print(repo, tid, exam_id, class_id, students_filter, *, include_booklet, personalize,
                        duplex, layout, filename):
    cls = await repo.get_class(tid, class_id)
    if cls is None:
        raise HTTPException(404, "Turma não encontrada")
    students = [StudentRef(UUID(s["id"]), s["name"], s["enrollment"]) for s in cls["students"]
                if students_filter is None or s["id"] == str(students_filter)]
    if not students:
        raise HTTPException(404 if students_filter else 409,
                            "Aluno não encontrado" if students_filter else "A turma não tem alunos")
    job = await _print_job(repo, tid, exam_id, cls["name"])
    await repo.lock_latest_version(tid, exam_id)         # a partir daqui, mudanças viram nova versão
    try:
        data, media = await render_bundle(job, students, config.QR_SECRET, include_booklet=include_booklet,
                                          personalize=personalize, duplex=duplex, layout=layout)
    except PdfRenderError as exc:
        raise HTTPException(503, "Não foi possível gerar o PDF. " + PDF_HINT + str(exc)) from exc
    ext = "zip" if media == "application/zip" else "pdf"
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}.{ext}"',
                             "X-Exam-Version": str(job.version)})


@router.get("/{exam_id}/classes/{class_id}/print")
async def print_class(exam_id: UUID, class_id: UUID,
                      layout: str = Query("single", pattern="^(single|zip)$"),
                      include_booklet: bool = True, personalize: bool = True, duplex: bool = False,
                      repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    exam = await _exam_or_404(repo, tid, exam_id)
    cls = await repo.get_class(tid, class_id)
    name = safe_filename(f"{exam['title']}_{cls['name'] if cls else ''}")
    return await _render_print(repo, tid, exam_id, class_id, None, include_booklet=include_booklet,
                               personalize=personalize, duplex=duplex, layout=layout, filename=name)


@router.get("/{exam_id}/classes/{class_id}/students/{student_id}/print")
async def print_student(exam_id: UUID, class_id: UUID, student_id: UUID, include_booklet: bool = True,
                        duplex: bool = False, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    exam = await _exam_or_404(repo, tid, exam_id)
    return await _render_print(repo, tid, exam_id, class_id, student_id, include_booklet=include_booklet,
                               personalize=True, duplex=duplex, layout="single",
                               filename=safe_filename(f"{exam['title']}_{student_id}"))


# ── notas em CSV ──────────────────────────────────────────────────────────────
@router.get("/{exam_id}/results.csv")
async def results_csv(exam_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    exam = await _exam_or_404(repo, tid, exam_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")                   # ";" abre direto no Excel em português
    w.writerow(["aluno", "nota", "nota_maxima", "acertos", "erros", "brancos", "anuladas",
                "pendentes_revisao", "corrigido_em"])
    for row in await repo.list_scans(tid, exam_id):
        loaded = await repo.load_scan(UUID(row["scan_id"]))
        if not loaded:
            continue
        ctx, res = loaded
        s = asdict(score_exam(res, ctx.answer_key, ctx.weights))
        fmt = lambda v: f"{v:.2f}".replace(".", ",")
        w.writerow([row["student_name"], fmt(s["points"]), fmt(s["max_points"]), s["correct"], s["wrong"],
                    s["blank"], s["annulled"], s["pending"], row["created_at"]])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="notas_{safe_filename(exam["title"])}.csv"'})
