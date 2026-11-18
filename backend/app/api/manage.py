"""Login, turmas, alunos, resultados e recortes. (Provas e impressão ficam em exams.py.)"""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import config
from app.api.scan import Repo, get_repo
from app.ratelimit import client_ip, login_limiter, register_limiter
from app.db.sqlite_repo import DuplicateError
from app.omr.grader import score_exam
from app.security import create_token, current_teacher_id, hash_password, verify_password

router = APIRouter()


# ── autenticação ──────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=2)
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/register", status_code=201)
async def register(body: RegisterIn, request: Request, repo=Depends(get_repo)):
    if not config.ALLOW_REGISTRATION:
        raise HTTPException(403, "Cadastro de novas contas está fechado neste servidor.")
    register_limiter.check(client_ip(request))
    try:
        tid = await repo.create_teacher(body.email, body.name, hash_password(body.password))
    except DuplicateError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"token": create_token(tid)}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, repo=Depends(get_repo)):
    login_limiter.check(f"{client_ip(request)}|{body.email.lower().strip()}")
    t = await repo.get_teacher_by_email(body.email)
    if not t or not verify_password(body.password, t["password_hash"]):
        raise HTTPException(401, "E-mail ou senha inválidos")
    return {"token": create_token(UUID(t["id"]))}


# ── turmas e alunos ───────────────────────────────────────────────────────────
class ClassIn(BaseModel):
    name: str = Field(min_length=1)


class StudentIn(BaseModel):
    name: str = Field(min_length=1)
    enrollment: str | None = None


@router.post("/classes", status_code=201)
async def create_class(body: ClassIn, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    return {"id": str(await repo.create_class(tid, body.name))}


@router.get("/classes")
async def list_classes(repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    return await repo.list_classes(tid)


@router.post("/classes/{class_id}/students", status_code=201)
async def add_student(class_id: UUID, body: StudentIn, repo=Depends(get_repo),
                      tid: UUID = Depends(current_teacher_id)):
    try:
        sid = await repo.add_student(tid, class_id, body.name, body.enrollment)
    except DuplicateError as exc:
        raise HTTPException(409, str(exc)) from exc
    if sid is None:
        raise HTTPException(404, "Turma não encontrada")
    return {"id": str(sid)}


class StudentsBulkIn(BaseModel):
    students: list[StudentIn] = Field(min_length=1, max_length=200)


@router.post("/classes/{class_id}/students/bulk", status_code=201)
async def add_students_bulk(class_id: UUID, body: StudentsBulkIn, repo=Depends(get_repo),
                            tid: UUID = Depends(current_teacher_id)):
    """Cadastro em lote (lista colada do diário/planilha). Matrículas repetidas são puladas."""
    created, skipped = [], []
    for st in body.students:
        try:
            sid = await repo.add_student(tid, class_id, st.name.strip(), (st.enrollment or None))
        except DuplicateError:
            skipped.append(st.name)
            continue
        if sid is None:
            raise HTTPException(404, "Turma não encontrada")
        created.append(str(sid))
    return {"created": created, "skipped": skipped}


@router.get("/classes/{class_id}")
async def get_class(class_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    cls = await repo.get_class(tid, class_id)
    if cls is None:
        raise HTTPException(404, "Turma não encontrada")
    return cls


@router.patch("/classes/{class_id}")
async def rename_class(class_id: UUID, body: ClassIn, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    if not await repo.rename_class(tid, class_id, body.name):
        raise HTTPException(404, "Turma não encontrada")
    return {"id": str(class_id), "name": body.name}


@router.delete("/classes/{class_id}", status_code=204)
async def delete_class(class_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    if not await repo.delete_class(tid, class_id):
        raise HTTPException(404, "Turma não encontrada")


@router.delete("/students/{student_id}", status_code=204)
async def delete_student(student_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    """Remove o aluno e, em cascata, as correções dele (direito de exclusão — LGPD)."""
    if not await repo.delete_student(tid, student_id):
        raise HTTPException(404, "Aluno não encontrado")


@router.get("/classes/{class_id}/students")
async def list_students(class_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    rows = await repo.list_students(tid, class_id)
    if rows is None:
        raise HTTPException(404, "Turma não encontrada")
    return rows


# ── resultados e recortes ─────────────────────────────────────────────────────
@router.get("/exams/{exam_id}/results")
async def results(exam_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    out = []
    for row in await repo.list_scans(tid, exam_id):
        loaded = await repo.load_scan(UUID(row["scan_id"]))
        if loaded:
            ctx, res = loaded
            out.append({**row, "score": asdict(score_exam(res, ctx.answer_key, ctx.weights)),
                        "review_needed": [r.number for r in res if r.needs_review]})
    return out


@router.get("/scans/{scan_id}")
async def scan_detail(scan_id: UUID, repo=Depends(get_repo), tid: UUID = Depends(current_teacher_id)):
    """Tudo que a tela de revisão precisa: aluno, prova, respostas lidas, gabarito e nota."""
    loaded = await repo.load_scan(scan_id)
    if loaded is None:
        raise HTTPException(404, "Scan não encontrado")
    ctx, res = loaded
    if ctx.teacher_id != tid:
        raise HTTPException(403, "Acesso negado")
    meta = await repo.get_scan_meta(scan_id)
    return {**meta, "options": ctx.spec.options, "answer_key": ctx.answer_key,
            "score": asdict(score_exam(res, ctx.answer_key, ctx.weights)),
            "answers": [{**asdict(r), "status": r.status.value} for r in res],
            "review_needed": [r.number for r in res if r.needs_review]}


@router.get("/scans/{scan_id}/answers/{question_number}/crop.png")
async def crop(scan_id: UUID, question_number: int, repo=Depends(get_repo),
               tid: UUID = Depends(current_teacher_id)):
    loaded = await repo.load_scan(scan_id)
    if loaded is None:
        raise HTTPException(404, "Scan não encontrado")
    if loaded[0].teacher_id != tid:
        raise HTTPException(403, "Acesso negado")
    path = await repo.get_crop_path(scan_id, question_number)
    if not path:
        raise HTTPException(404, "Esta questão não tem recorte")
    return FileResponse(path, media_type="image/png")
