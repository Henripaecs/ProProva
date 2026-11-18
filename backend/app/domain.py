from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.omr.layout import AnswerGridSpec


@dataclass
class ExamContext:
    spec: AnswerGridSpec
    answer_key: dict[int, str | list[str] | None]
    weights: dict[int, float] | None = None
    teacher_id: UUID | None = None          # dono da prova (controle de acesso)
