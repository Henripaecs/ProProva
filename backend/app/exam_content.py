"""
Conteúdo da prova (saída do editor): questões, alternativas, imagens e estilo do caderno.

O conteúdo é a FONTE do gabarito: cada questão diz qual alternativa é a correta, e daí saem
n_questions, n_options, answer_key e weights do cartão-resposta. Assim o caderno impresso e o
cartão nunca discordam sobre quantas questões/alternativas existem.

Texto com marcação simples e segura (o HTML digitado é sempre escapado):
  **negrito**   *itálico*   __sublinhado__   ^sobrescrito^   ~subscrito~   quebra de linha = nova linha
"""
from __future__ import annotations

import re
from typing import Literal

from markupsafe import Markup, escape
from pydantic import BaseModel, Field, field_validator, model_validator

LETTERS = "ABCDEF"

FONT_STACKS = {
    "serif": '"Times New Roman", "Liberation Serif", "DejaVu Serif", Georgia, serif',
    "sans": 'Arial, "Liberation Sans", "DejaVu Sans", Helvetica, sans-serif',
    "mono": '"Courier New", "Liberation Mono", "DejaVu Sans Mono", monospace',
}


class QuestionIn(BaseModel):
    stem: str = Field("", max_length=8000)                 # enunciado
    image: str | None = None                               # id de imagem enviada (POST /exams/{id}/assets)
    image_width: int = Field(60, ge=15, le=100)            # % da largura da coluna
    options: list[str] = Field(min_length=2, max_length=6)
    option_images: list[str | None] = Field(default_factory=list, max_length=6)   # imagem por alternativa (opcional)
    option_image_height: int = Field(28, ge=10, le=80)     # altura máx. das imagens das alternativas (mm)
    section: str = Field("", max_length=200)               # título de seção ANTES desta questão (ex.: "Matemática")
    section_text: str = Field("", max_length=8000)         # texto de apoio da seção (opcional)
    correct: str | list[str] | None                        # "B" | ["A","C"] | null = anulada
    weight: float = Field(1.0, gt=0, le=100)

    @field_validator("options")
    @classmethod
    def _opts(cls, v: list[str]) -> list[str]:
        if any(len(o) > 2000 for o in v):
            raise ValueError("Alternativa longa demais (máx. 2000 caracteres)")
        return v

    @model_validator(mode="after")
    def _option_images(self) -> "QuestionIn":
        if len(self.option_images) > len(self.options):
            raise ValueError("Há mais imagens de alternativa do que alternativas")
        self.option_images = (list(self.option_images) + [None] * len(self.options))[: len(self.options)]
        for i, (txt, img) in enumerate(zip(self.options, self.option_images)):
            if not txt.strip() and not img:
                raise ValueError(f"A alternativa {LETTERS[i]} está vazia (coloque texto ou imagem)")
        return self

    @model_validator(mode="after")
    def _correct(self) -> "QuestionIn":
        valid = LETTERS[: len(self.options)]
        letters = [] if self.correct is None else ([self.correct] if isinstance(self.correct, str) else self.correct)
        letters = [l.strip().upper() for l in letters]
        if any(l not in valid for l in letters):
            raise ValueError(f"Resposta correta deve ser uma de {list(valid)}")
        if isinstance(self.correct, list) and not letters:
            raise ValueError("Lista de corretas vazia; use null para anular a questão")
        self.correct = None if not letters else (letters[0] if isinstance(self.correct, str) else letters)
        return self


class HeaderIn(BaseModel):
    school: str = Field("", max_length=200)
    subtitle: str = Field("", max_length=200)              # disciplina, professor, bimestre…
    instructions: str = Field("", max_length=3000)
    show_grade_box: bool = True
    logo: str | None = None                                # imagem enviada (POST /exams/{id}/assets)
    show_logo: bool = True                                 # o professor pode guardar a logo e não usá-la


class StyleIn(BaseModel):
    font_family: Literal["serif", "sans", "mono"] = "serif"
    font_size_pt: float = Field(11, ge=8, le=16)
    columns: Literal[1, 2] = 2
    line_height: float = Field(1.35, ge=1.0, le=2.0)
    option_layout: Literal["vertical", "horizontal"] = "vertical"
    show_points: bool = False                              # mostra "(2,0 pts)" ao lado do número
    column_rule: bool = True                               # linha fina entre colunas


class ExamContent(BaseModel):
    header: HeaderIn = HeaderIn()
    questions: list[QuestionIn] = Field(min_length=1, max_length=120)


def derive_grid(content: ExamContent) -> tuple[int, int, dict[int, str | list[str] | None], dict[int, float] | None]:
    """Conteúdo → (n_questions, n_options, answer_key, weights)."""
    qs = content.questions
    n_options = max(len(q.options) for q in qs)
    key = {i + 1: q.correct for i, q in enumerate(qs)}
    weights = {i + 1: q.weight for i, q in enumerate(qs) if q.weight != 1.0}
    return len(qs), n_options, key, (weights or None)


def asset_ids(content: ExamContent) -> set[str]:
    ids = {q.image for q in content.questions if q.image}
    ids |= {img for q in content.questions for img in q.option_images if img}
    if content.header.logo:
        ids.add(content.header.logo)
    return ids


# ── marcação segura → HTML ──────────────────────────────────────────────────────
_RULES = [
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__", re.S), r"<u>\1</u>"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S), r"<i>\1</i>"),
    (re.compile(r"\^(\S[^^\n]*?)\^"), r"<sup>\1</sup>"),
    (re.compile(r"~(\S[^~\n]*?)~"), r"<sub>\1</sub>"),
]


def rich(text: str) -> Markup:
    """Escapa TODO o HTML e só então aplica a marcação permitida (sem risco de injeção)."""
    out = str(escape(text.strip()))
    for rx, rep in _RULES:
        out = rx.sub(rep, out)
    return Markup(out.replace("\r\n", "\n").replace("\n", "<br>"))
