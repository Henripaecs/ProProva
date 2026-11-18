"""
Payload do QR Code: compacto (QR pequeno = leitura robusta) e ASSINADO (HMAC), para que
um QR adulterado ou de outro sistema seja rejeitado antes de tocar no banco.

Formato:  OMR1|<exam_id>|<student_id>|<version>|<sig>
  - ids: UUID em base64url sem padding (22 chars)
  - sig: primeiros 8 bytes do HMAC-SHA256, base64url
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from uuid import UUID

from .errors import InvalidQRError

_PREFIX = "OMR1"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def _sign(body: str, secret: bytes) -> str:
    return _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest()[:8])


@dataclass(frozen=True)
class SheetPayload:
    exam_id: UUID
    student_id: UUID
    version: int


def encode_payload(p: SheetPayload, secret: bytes) -> str:
    body = f"{_PREFIX}|{_b64(p.exam_id.bytes)}|{_b64(p.student_id.bytes)}|{p.version}"
    return f"{body}|{_sign(body, secret)}"


def decode_payload(text: str, secret: bytes) -> SheetPayload:
    try:
        prefix, exam, student, version, sig = text.strip().split("|")
        if prefix != _PREFIX:
            raise ValueError("prefixo desconhecido")
        body = f"{prefix}|{exam}|{student}|{version}"
        if not hmac.compare_digest(sig, _sign(body, secret)):
            raise ValueError("assinatura inválida")
        return SheetPayload(UUID(bytes=_unb64(exam)), UUID(bytes=_unb64(student)), int(version))
    except (ValueError, TypeError) as exc:
        raise InvalidQRError("QR Code não pertence a este sistema ou foi adulterado.",
                             hint="Confira se a folha é um cartão-resposta gerado pelo app.") from exc
