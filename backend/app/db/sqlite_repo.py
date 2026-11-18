"""
Repositório SQLite (dev/testes). Implementa o Protocol `Repo` de app/api/scan.py.
sqlite3 é síncrono: cada método roda numa thread (asyncio.to_thread) para não travar o servidor.
Para produção, crie um PostgresRepo com a mesma interface sobre database/schema.sql.
"""
from __future__ import annotations

import asyncio
import functools
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from app.domain import ExamContext
from app.omr.grader import MarkStatus, QuestionResult
from app.omr.layout import AnswerGridSpec

SCHEMA = Path(__file__).resolve().parents[3] / "database" / "schema_sqlite.sql"


class DuplicateError(Exception):
    pass


def threaded(fn):
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        return await asyncio.to_thread(fn, self, *args, **kwargs)
    return wrapper


def _int_keys(raw: str | None):
    return None if raw is None else {int(k): v for k, v in json.loads(raw).items()}


class SqliteRepo:
    def __init__(self, db_path: str | Path, data_dir: str | Path):
        self.db_path, self.data_dir = str(db_path), Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._tx() as c:
            c.executescript(SCHEMA.read_text(encoding="utf-8"))

    @contextmanager
    def _tx(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── professores ───────────────────────────────────────────────────────────
    @threaded
    def create_teacher(self, email: str, name: str, password_hash: str) -> UUID:
        tid = uuid4()
        try:
            with self._tx() as c:
                c.execute("INSERT INTO teachers(id,email,name,password_hash) VALUES(?,?,?,?)",
                          (str(tid), email.lower().strip(), name, password_hash))
        except sqlite3.IntegrityError as exc:
            raise DuplicateError("E-mail já cadastrado") from exc
        return tid

    @threaded
    def get_teacher_by_email(self, email: str) -> dict | None:
        with self._tx() as c:
            row = c.execute("SELECT * FROM teachers WHERE email=?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None

    # ── turmas e alunos ───────────────────────────────────────────────────────
    @threaded
    def create_class(self, teacher_id: UUID, name: str) -> UUID:
        cid = uuid4()
        with self._tx() as c:
            c.execute("INSERT INTO classes(id,teacher_id,name) VALUES(?,?,?)", (str(cid), str(teacher_id), name))
        return cid

    @threaded
    def list_classes(self, teacher_id: UUID) -> list[dict]:
        with self._tx() as c:
            return [dict(r) for r in c.execute("SELECT id,name FROM classes WHERE teacher_id=? ORDER BY name",
                                               (str(teacher_id),))]

    @threaded
    def add_student(self, teacher_id: UUID, class_id: UUID, name: str, enrollment: str | None) -> UUID | None:
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",
                             (str(class_id), str(teacher_id))).fetchone():
                return None
            sid = uuid4()
            try:
                c.execute("INSERT INTO students(id,class_id,name,enrollment) VALUES(?,?,?,?)",
                          (str(sid), str(class_id), name, enrollment))
            except sqlite3.IntegrityError as exc:
                raise DuplicateError("Matrícula já cadastrada nesta turma") from exc
        return sid

    @threaded
    def list_students(self, teacher_id: UUID, class_id: UUID) -> list[dict] | None:
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",
                             (str(class_id), str(teacher_id))).fetchone():
                return None
            return [dict(r) for r in c.execute("SELECT id,name,enrollment FROM students WHERE class_id=? ORDER BY name",
                                               (str(class_id),))]

    @threaded
    def delete_class(self, teacher_id: UUID, class_id: UUID) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM classes WHERE id=? AND teacher_id=?",
                             (str(class_id), str(teacher_id))).rowcount > 0

    @threaded
    def rename_class(self, teacher_id: UUID, class_id: UUID, name: str) -> bool:
        with self._tx() as c:
            return c.execute("UPDATE classes SET name=? WHERE id=? AND teacher_id=?",
                             (name, str(class_id), str(teacher_id))).rowcount > 0

    @threaded
    def delete_student(self, teacher_id: UUID, student_id: UUID) -> bool:
        with self._tx() as c:
            return c.execute("""DELETE FROM students WHERE id=? AND class_id IN
                                (SELECT id FROM classes WHERE teacher_id=?)""",
                             (str(student_id), str(teacher_id))).rowcount > 0

    @threaded
    def get_class(self, teacher_id: UUID, class_id: UUID) -> dict | None:
        with self._tx() as c:
            row = c.execute("SELECT id,name FROM classes WHERE id=? AND teacher_id=?",
                            (str(class_id), str(teacher_id))).fetchone()
            if not row:
                return None
            students = [dict(r) for r in c.execute(
                "SELECT id,name,enrollment FROM students WHERE class_id=? ORDER BY name", (str(class_id),))]
        return {**dict(row), "students": students}

    # ── provas ────────────────────────────────────────────────────────────────
    @threaded
    def create_exam(self, teacher_id: UUID, title: str, spec: AnswerGridSpec,
                    answer_key: dict[int, str | list[str] | None], weights: dict[int, float] | None,
                    content: dict | None = None, style: dict | None = None) -> UUID:
        eid = uuid4()
        with self._tx() as c:
            c.execute("INSERT INTO exams(id,teacher_id,title) VALUES(?,?,?)", (str(eid), str(teacher_id), title))
            c.execute("""INSERT INTO exam_versions(id,exam_id,version,content,style,grid_spec,answer_key,weights)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (str(uuid4()), str(eid), 1, json.dumps(content or {}), json.dumps(style or {}),
                       spec.to_json(), json.dumps(answer_key), json.dumps(weights) if weights else None))
        return eid

    @threaded
    def update_exam(self, teacher_id: UUID, exam_id: UUID, title: str, spec: AnswerGridSpec,
                    answer_key: dict, weights: dict | None, content: dict | None,
                    style: dict | None) -> dict | None:
        """Atualiza a versão atual; se ela já foi impressa (travada), cria a versão seguinte.
        Cartões já impressos continuam válidos: o QR deles aponta para a versão antiga."""
        with self._tx() as c:
            ev = c.execute("""SELECT ev.id, ev.version, ev.locked_at FROM exams e JOIN exam_versions ev
                              ON ev.exam_id=e.id WHERE e.id=? AND e.teacher_id=?
                              ORDER BY ev.version DESC LIMIT 1""", (str(exam_id), str(teacher_id))).fetchone()
            if not ev:
                return None
            c.execute("UPDATE exams SET title=? WHERE id=?", (title, str(exam_id)))
            vals = (json.dumps(content or {}), json.dumps(style or {}), spec.to_json(), json.dumps(answer_key),
                    json.dumps(weights) if weights else None)
            if ev["locked_at"] is None:
                c.execute("""UPDATE exam_versions SET content=?,style=?,grid_spec=?,answer_key=?,weights=?
                             WHERE id=?""", (*vals, ev["id"]))
                return {"version": ev["version"], "new_version": False}
            version = ev["version"] + 1
            c.execute("""INSERT INTO exam_versions(id,exam_id,version,content,style,grid_spec,answer_key,weights)
                         VALUES(?,?,?,?,?,?,?,?)""", (str(uuid4()), str(exam_id), version, *vals))
            return {"version": version, "new_version": True}

    @threaded
    def list_exams(self, teacher_id: UUID) -> list[dict]:
        with self._tx() as c:
            rows = c.execute(
                """SELECT e.id, e.title, e.created_at, ev.version, ev.grid_spec, ev.locked_at, ev.content,
                          (SELECT COUNT(*) FROM scans sc JOIN exam_versions v2 ON v2.id=sc.exam_version_id
                           WHERE v2.exam_id=e.id AND sc.is_current=1) AS n_scans
                   FROM exams e JOIN exam_versions ev ON ev.exam_id=e.id
                   WHERE e.teacher_id=? AND ev.version=(SELECT MAX(version) FROM exam_versions WHERE exam_id=e.id)
                   ORDER BY e.created_at DESC""", (str(teacher_id),)).fetchall()
        out = []
        for r in rows:
            spec = json.loads(r["grid_spec"])
            out.append({"id": r["id"], "title": r["title"], "created_at": r["created_at"], "version": r["version"],
                        "n_questions": spec["n_questions"], "n_options": spec["n_options"],
                        "locked": r["locked_at"] is not None, "has_booklet": bool(json.loads(r["content"])),
                        "n_scans": r["n_scans"]})
        return out

    @threaded
    def get_exam(self, teacher_id: UUID, exam_id: UUID) -> dict | None:
        with self._tx() as c:
            r = c.execute("""SELECT e.id, e.title, ev.version, ev.content, ev.style, ev.grid_spec, ev.answer_key,
                                    ev.weights, ev.locked_at
                             FROM exams e JOIN exam_versions ev ON ev.exam_id=e.id
                             WHERE e.id=? AND e.teacher_id=? ORDER BY ev.version DESC LIMIT 1""",
                          (str(exam_id), str(teacher_id))).fetchone()
        if not r:
            return None
        return {"id": r["id"], "title": r["title"], "version": r["version"], "locked": r["locked_at"] is not None,
                "content": json.loads(r["content"]) or None, "style": json.loads(r["style"]) or None,
                "grid_spec": json.loads(r["grid_spec"]), "answer_key": json.loads(r["answer_key"]),
                "weights": json.loads(r["weights"]) if r["weights"] else None}

    @threaded
    def delete_exam(self, teacher_id: UUID, exam_id: UUID) -> list[str] | None:
        """Apaga a prova; devolve os caminhos de arquivos (recortes/imagens) para remoção."""
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM exams WHERE id=? AND teacher_id=?",
                             (str(exam_id), str(teacher_id))).fetchone():
                return None
            files = [r[0] for r in c.execute(
                """SELECT sa.crop_path FROM scan_answers sa JOIN scans sc ON sc.id=sa.scan_id
                   JOIN exam_versions ev ON ev.id=sc.exam_version_id
                   WHERE ev.exam_id=? AND sa.crop_path IS NOT NULL""", (str(exam_id),))]
            files += [r[0] for r in c.execute("SELECT path FROM exam_assets WHERE exam_id=?", (str(exam_id),))]
            c.execute("DELETE FROM exams WHERE id=?", (str(exam_id),))
        return files

    # ── imagens das questões ──────────────────────────────────────────────────
    @threaded
    def add_asset(self, teacher_id: UUID, exam_id: UUID, mime: str, data: bytes, ext: str) -> UUID | None:
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM exams WHERE id=? AND teacher_id=?",
                             (str(exam_id), str(teacher_id))).fetchone():
                return None
            aid = uuid4()
            folder = self.data_dir / "assets" / str(exam_id)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{aid}.{ext}"
            path.write_bytes(data)
            c.execute("INSERT INTO exam_assets(id,exam_id,mime,path) VALUES(?,?,?,?)",
                      (str(aid), str(exam_id), mime, str(path)))
        return aid

    @threaded
    def get_asset(self, teacher_id: UUID, exam_id: UUID, asset_id: UUID) -> tuple[str, str] | None:
        with self._tx() as c:
            r = c.execute("""SELECT a.mime, a.path FROM exam_assets a JOIN exams e ON e.id=a.exam_id
                             WHERE a.id=? AND a.exam_id=? AND e.teacher_id=?""",
                          (str(asset_id), str(exam_id), str(teacher_id))).fetchone()
        return (r["mime"], r["path"]) if r else None

    @threaded
    def load_assets(self, exam_id: UUID, ids: set[str]) -> dict[str, tuple[str, bytes]]:
        if not ids:
            return {}
        with self._tx() as c:
            rows = c.execute(f"SELECT id, mime, path FROM exam_assets WHERE exam_id=? AND id IN "
                             f"({','.join('?' * len(ids))})", (str(exam_id), *ids)).fetchall()
        out = {}
        for r in rows:
            p = Path(r["path"])
            if p.exists():
                out[r["id"]] = (r["mime"], p.read_bytes())
        return out

    # ── impressão ─────────────────────────────────────────────────────────────
    @threaded
    def get_sheet_info(self, teacher_id: UUID, exam_id: UUID, student_id: UUID) -> dict | None:
        """Dados para imprimir o cartão (e trava a versão na 1ª impressão). None se não for do professor."""
        with self._tx() as c:
            row = c.execute(
                """SELECT e.title, ev.id AS ev_id, ev.version, ev.grid_spec, s.name AS student_name, cl.name AS class_name
                   FROM exams e JOIN exam_versions ev ON ev.exam_id=e.id
                   JOIN students s ON s.id=? JOIN classes cl ON cl.id=s.class_id AND cl.teacher_id=e.teacher_id
                   WHERE e.id=? AND e.teacher_id=? ORDER BY ev.version DESC LIMIT 1""",
                (str(student_id), str(exam_id), str(teacher_id))).fetchone()
            if not row:
                return None
            c.execute("UPDATE exam_versions SET locked_at=COALESCE(locked_at, datetime('now')) WHERE id=?", (row["ev_id"],))
        return {"title": row["title"], "version": row["version"], "student_name": row["student_name"],
                "class_name": row["class_name"], "spec": AnswerGridSpec.from_json(row["grid_spec"])}

    @threaded
    def lock_latest_version(self, teacher_id: UUID, exam_id: UUID) -> None:
        with self._tx() as c:
            c.execute("""UPDATE exam_versions SET locked_at=COALESCE(locked_at, datetime('now'))
                         WHERE exam_id=? AND version=(SELECT MAX(version) FROM exam_versions WHERE exam_id=?)
                         AND exam_id IN (SELECT id FROM exams WHERE teacher_id=?)""",
                      (str(exam_id), str(exam_id), str(teacher_id)))

    @threaded
    def get_exam_context(self, exam_id: UUID, version: int) -> ExamContext | None:
        with self._tx() as c:
            row = c.execute(
                """SELECT e.teacher_id, ev.grid_spec, ev.answer_key, ev.weights FROM exams e
                   JOIN exam_versions ev ON ev.exam_id=e.id WHERE e.id=? AND ev.version=?""",
                (str(exam_id), version)).fetchone()
        return self._ctx(row)

    @staticmethod
    def _ctx(row) -> ExamContext | None:
        if not row:
            return None
        return ExamContext(AnswerGridSpec.from_json(row["grid_spec"]), _int_keys(row["answer_key"]),
                           _int_keys(row["weights"]), UUID(row["teacher_id"]))

    # ── correções ─────────────────────────────────────────────────────────────
    @threaded
    def create_scan(self, exam_id: UUID, student_id: UUID, version: int,
                    results: list[QuestionResult], crops: dict[int, bytes]) -> UUID:
        scan_id = str(uuid4())
        with self._tx() as c:
            ev = c.execute("SELECT id FROM exam_versions WHERE exam_id=? AND version=?",
                           (str(exam_id), version)).fetchone()
            if not ev:
                raise LookupError("Versão da prova não encontrada")
            try:
                c.execute("UPDATE scans SET is_current=0 WHERE exam_version_id=? AND student_id=?",
                          (ev["id"], str(student_id)))
                c.execute("INSERT INTO scans(id,exam_version_id,student_id) VALUES(?,?,?)",
                          (scan_id, ev["id"], str(student_id)))
            except sqlite3.IntegrityError as exc:
                raise LookupError("Aluno do QR Code não existe mais") from exc
            crop_dir = self.data_dir / "crops" / scan_id
            crop_dir.mkdir(parents=True, exist_ok=True)
            rows = []
            for r in results:
                path = None
                if r.number in crops:
                    p = crop_dir / f"{r.number}.png"
                    p.write_bytes(crops[r.number])
                    path = str(p)
                rows.append((scan_id, r.number, r.status.value, json.dumps(r.fills), json.dumps(r.marked),
                             r.answer, r.source, int(r.needs_review), r.confidence, path))
            c.executemany("""INSERT INTO scan_answers(scan_id,question_number,status,fills,marked,final_answer,
                             source,needs_review,confidence,crop_path) VALUES(?,?,?,?,?,?,?,?,?,?)""", rows)
        return UUID(scan_id)

    @threaded
    def load_scan(self, scan_id: UUID) -> tuple[ExamContext, list[QuestionResult]] | None:
        with self._tx() as c:
            row = c.execute(
                """SELECT e.teacher_id, ev.grid_spec, ev.answer_key, ev.weights FROM scans sc
                   JOIN exam_versions ev ON ev.id=sc.exam_version_id JOIN exams e ON e.id=ev.exam_id
                   WHERE sc.id=?""", (str(scan_id),)).fetchone()
            if not row:
                return None
            answers = c.execute("SELECT * FROM scan_answers WHERE scan_id=? ORDER BY question_number",
                                (str(scan_id),)).fetchall()
        results = [QuestionResult(a["question_number"], MarkStatus(a["status"]), json.loads(a["fills"]),
                                  json.loads(a["marked"]), a["final_answer"], a["confidence"],
                                  needs_review=bool(a["needs_review"]), source=a["source"]) for a in answers]
        return self._ctx(row), results

    @threaded
    def save_review(self, scan_id: UUID, question_number: int, answer: str | None, reviewer_id: UUID) -> None:
        with self._tx() as c:
            c.execute("""UPDATE scan_answers SET final_answer=?, status=?, source='human', needs_review=0,
                         confidence=1, reviewed_by=? WHERE scan_id=? AND question_number=?""",
                      (answer, "blank" if answer is None else "single", str(reviewer_id),
                       str(scan_id), question_number))

    @threaded
    def get_crop_path(self, scan_id: UUID, question_number: int) -> str | None:
        with self._tx() as c:
            row = c.execute("SELECT crop_path FROM scan_answers WHERE scan_id=? AND question_number=?",
                            (str(scan_id), question_number)).fetchone()
        return row["crop_path"] if row else None

    @threaded
    def list_scans(self, teacher_id: UUID, exam_id: UUID) -> list[dict]:
        with self._tx() as c:
            return [dict(r) for r in c.execute(
                """SELECT sc.id AS scan_id, s.id AS student_id, s.name AS student_name, sc.created_at
                   FROM scans sc JOIN exam_versions ev ON ev.id=sc.exam_version_id JOIN exams e ON e.id=ev.exam_id
                   JOIN students s ON s.id=sc.student_id
                   WHERE e.id=? AND e.teacher_id=? AND sc.is_current=1 ORDER BY s.name""",
                (str(exam_id), str(teacher_id)))]

    @threaded
    def get_scan_meta(self, scan_id: UUID) -> dict | None:
        with self._tx() as c:
            r = c.execute("""SELECT sc.id, sc.created_at, sc.is_current, s.id AS student_id, s.name AS student_name,
                                    e.id AS exam_id, e.title AS exam_title, ev.version
                             FROM scans sc JOIN students s ON s.id=sc.student_id
                             JOIN exam_versions ev ON ev.id=sc.exam_version_id JOIN exams e ON e.id=ev.exam_id
                             WHERE sc.id=?""", (str(scan_id),)).fetchone()
        return dict(r) if r else None

    @threaded
    def purge_scans_before(self, iso_datetime: str) -> int:
        """Retenção (LGPD): apaga correções antigas e seus recortes. Devolve quantas apagou."""
        with self._tx() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM scans WHERE created_at < ?", (iso_datetime,))]
            c.executemany("DELETE FROM scans WHERE id=?", [(i,) for i in ids])
        for i in ids:
            folder = self.data_dir / "crops" / i
            if folder.exists():
                for f in folder.iterdir():
                    f.unlink(missing_ok=True)
                folder.rmdir()
        return len(ids)
