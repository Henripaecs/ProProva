"""Erros de domínio. Cada um carrega um `code` estável e uma `hint` amigável para o app mobile exibir."""
from __future__ import annotations


class OMRError(Exception):
    code = "omr_error"

    def __init__(self, message: str, hint: str | None = None, issues: list[str] | None = None):
        super().__init__(message)
        self.hint = hint
        self.issues = issues or []

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "hint": self.hint, "issues": self.issues}


class MarkersNotFoundError(OMRError):
    code = "markers_not_found"


class QRNotFoundError(OMRError):
    code = "qr_not_found"


class InvalidQRError(OMRError):
    code = "invalid_qr"


class ImageDecodeError(OMRError):
    code = "image_decode_failed"
