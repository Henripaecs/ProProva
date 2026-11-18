"""Configuração por variáveis de ambiente (valores padrão servem só para desenvolvimento)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV = os.environ.get("APP_ENV", "dev").lower()            # dev | production
IS_PRODUCTION = ENV == "production"

_DEV_QR, _DEV_AUTH = "dev-qr-secret-troque", "dev-auth-secret-troque"
QR_SECRET = os.environ.get("QR_SECRET", _DEV_QR).encode()
AUTH_SECRET = os.environ.get("AUTH_SECRET", _DEV_AUTH).encode()
DATA_DIR = Path(os.environ.get("DATA_DIR", BACKEND_DIR / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "exam.db"))
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]

# Na internet, feche o cadastro depois de criar a(s) conta(s): ALLOW_REGISTRATION=false
ALLOW_REGISTRATION = os.environ.get("ALLOW_REGISTRATION", "true").lower() in ("1", "true", "yes", "sim")
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "14"))     # quantos backups diários manter


def check_production() -> None:
    """Em produção, recusa subir com os segredos de exemplo (qualquer um forjaria tokens e QR Codes)."""
    if not IS_PRODUCTION:
        return
    problems = []
    for name, val, dev in (("QR_SECRET", QR_SECRET, _DEV_QR), ("AUTH_SECRET", AUTH_SECRET, _DEV_AUTH)):
        if val.decode() == dev or len(val) < 32:
            problems.append(f"{name} ausente ou curto (use 32+ caracteres aleatórios)")
    if QR_SECRET == AUTH_SECRET:
        problems.append("QR_SECRET e AUTH_SECRET devem ser diferentes")
    if problems:
        raise RuntimeError("Configuração insegura para produção: " + "; ".join(problems))
