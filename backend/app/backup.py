"""
Backup do sistema: banco SQLite (cópia consistente, mesmo com a API rodando) + imagens das questões
+ recortes das rasuras, num único .zip em DATA_DIR/backups. Mantém os BACKUP_KEEP mais recentes.

  python -m app.backup                      (no servidor: docker compose exec api python -m app.backup)
  python -m app.backup --restore arquivo.zip   (com a API PARADA)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app import config


def make_backup(db_path: Path = config.DB_PATH, data_dir: Path = config.DATA_DIR,
                keep: int = config.BACKUP_KEEP) -> Path:
    out_dir = data_dir / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = out_dir / f"backup_{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "exam.db"
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snap)
        try:
            src.backup(dst)                    # API oficial do SQLite: cópia íntegra com o banco em uso
        finally:
            dst.close()
            src.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snap, "exam.db")
            for sub in ("assets", "crops"):
                for f in (data_dir / sub).rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(data_dir).as_posix())
    old = sorted(out_dir.glob("backup_*.zip"))[:-keep] if keep > 0 else []
    for f in old:
        f.unlink(missing_ok=True)
    return target


def restore(zip_path: Path, data_dir: Path = config.DATA_DIR, db_path: Path = config.DB_PATH) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "exam.db" not in names:
            raise SystemExit("Arquivo não parece um backup deste sistema (sem exam.db).")
        if db_path.exists():
            db_path.rename(db_path.with_suffix(f".antes-restauracao-{datetime.now():%Y%m%d%H%M%S}.db"))
        for n in names:
            if n == "exam.db":
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.write_bytes(zf.read(n))
            elif n.startswith(("assets/", "crops/")) and ".." not in n:
                dest = data_dir / n
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(n))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", type=Path)
    a = ap.parse_args()
    if a.restore:
        restore(a.restore)
        print("Backup restaurado. Suba a API de novo.")
    else:
        p = make_backup()
        print(f"Backup criado: {p} ({p.stat().st_size / 1e6:.1f} MB)")
    sys.exit(0)
