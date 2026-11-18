"""Senha (scrypt) e token assinado (HMAC) — só biblioteca padrão, sem dependências extras."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

TOKEN_TTL_S = 12 * 3600
_bearer = HTTPBearer(auto_error=False)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(test, _unb64(digest))
    except Exception:
        return False


def create_token(teacher_id: UUID) -> str:
    body = _b64(json.dumps({"sub": str(teacher_id), "exp": int(time.time()) + TOKEN_TTL_S}).encode())
    sig = _b64(hmac.new(config.AUTH_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def current_teacher_id(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> UUID:
    unauthorized = HTTPException(401, "Token ausente, inválido ou expirado",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        body, sig = creds.credentials.split(".")
        expected = _b64(hmac.new(config.AUTH_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        data = json.loads(_unb64(body))
        if data["exp"] < time.time():
            raise ValueError
        return UUID(data["sub"])
    except Exception:
        raise unauthorized
