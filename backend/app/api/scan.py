"""
API de correção (sem IA externa). Todas as rotas exigem login.
  POST /v1/scan                                 foto → respostas + nota (parcial se houver rasuras)
  GET  /v1/scans/{id}/review                    questões que aguardam o professor
  PUT  /v1/scans/{id}/answers/{n}               professor decide a questão n → nota recalculada
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Protocol
from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import config
from app.domain import ExamContext
from app.omr.errors import ImageDecodeError, OMRError
from app.omr.grader import (QuestionResult, apply_human_review, crop_question_row, grade_roi,
                            score_exam)
from app.omr.qr import decode_payload
from app.omr.sheet_aligner import align_sheet
from app.security import current_teacher_id

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
router = APIRouter()


class Repo(Protocol):
    async def get_exam_context(self, exam_id: UUID, version: int) -> ExamContext | None: ...
    async def create_scan(self, exam_id: UUID, student_id: UUID, version: int,
                          results: list[QuestionResult], crops: dict[int, bytes]) -> UUID: ...
    async def load_scan(self, scan_id: UUID) -> tuple[ExamContext, list[QuestionResult]] | None: ...
    async def save_review(self, scan_id: UUID, question_number: int, answer: str | None,
                          reviewer_id: UUID) -> None: ...


def get_repo() -> Repo:                      # sobrescrito em main.py
    raise NotImplementedError


def _answers_json(results: list[QuestionResult]) -> list[dict]:
    return [{**asdict(r), "status": r.status.value} for r in results]


def _owned(ctx_results, teacher_id: UUID):
    """404 se não existe; 403 se existe mas é de outro professor."""
    if ctx_results is None:
        raise HTTPException(404, "Scan não encontrado")
    if ctx_results[0].teacher_id != teacher_id:
        raise HTTPException(403, "Acesso negado")
    return ctx_results


@router.post("/scan")
async def scan(file: UploadFile = File(...), repo: Repo = Depends(get_repo),
               teacher_id: UUID = Depends(current_teacher_id)):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Imagem grande demais")
    bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)   # aplica orientação EXIF
    if bgr is None:
        raise ImageDecodeError("Arquivo não é uma imagem válida.")

    aligned = align_sheet(bgr)                                           # foto → ROI
    payload = decode_payload(aligned.qr_text, config.QR_SECRET)          # QR assinado
    ctx = await repo.get_exam_context(payload.exam_id, payload.version)
    if ctx is None:
        raise HTTPException(404, "Prova/versão não encontrada")
    if ctx.teacher_id != teacher_id:
        raise HTTPException(403, "Esta prova pertence a outro professor")

    results = grade_roi(aligned.roi, ctx.spec)                           # OMR
    crops = {r.number: crop_question_row(aligned.roi, ctx.spec, r.number)
             for r in results if r.needs_review}                         # recortes p/ o painel
    try:
        scan_id = await repo.create_scan(payload.exam_id, payload.student_id, payload.version, results, crops)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    score = score_exam(results, ctx.answer_key, ctx.weights)
    return {"scan_id": str(scan_id), "exam_id": str(payload.exam_id),
            "student_id": str(payload.student_id), "version": payload.version,
            "review_needed": [r.number for r in results if r.needs_review],
            "score": asdict(score), "answers": _answers_json(results)}


@router.get("/scans/{scan_id}/review")
async def pending_review(scan_id: UUID, repo: Repo = Depends(get_repo),
                         teacher_id: UUID = Depends(current_teacher_id)):
    _, results = _owned(await repo.load_scan(scan_id), teacher_id)
    return [{"question": r.number, "status": r.status.value, "fills": r.fills, "marked": r.marked}
            for r in results if r.needs_review]


class ReviewIn(BaseModel):
    answer: str | None = None        # "A".."E" ou null (= em branco)


@router.put("/scans/{scan_id}/answers/{question_number}")
async def review_answer(scan_id: UUID, question_number: int, body: ReviewIn,
                        repo: Repo = Depends(get_repo), teacher_id: UUID = Depends(current_teacher_id)):
    ctx, results = _owned(await repo.load_scan(scan_id), teacher_id)
    target = next((r for r in results if r.number == question_number), None)
    if target is None:
        raise HTTPException(404, "Questão não encontrada")
    try:
        apply_human_review(target, body.answer, ctx.spec)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await repo.save_review(scan_id, question_number, target.answer, teacher_id)
    score = score_exam(results, ctx.answer_key, ctx.weights)             # nota recalculada
    return {"score": asdict(score), "review_needed": [r.number for r in results if r.needs_review]}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(OMRError)
    async def _omr_handler(_: Request, exc: OMRError):
        return JSONResponse(status_code=422, content=exc.to_dict())
