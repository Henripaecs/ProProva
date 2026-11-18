"""Proteções de produção: segredos obrigatórios, cadastro fechado, limite de tentativas, backup/restauração.
Rode:  cd backend && python ../tests/test_production.py"""
import importlib, os, sqlite3, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def check(cond, msg):
    print(("  ok  " if cond else " FAIL ") + msg)
    if not cond:
        sys.exit(1)


def fresh(env: dict):
    for k in ("APP_ENV", "QR_SECRET", "AUTH_SECRET", "ALLOW_REGISTRATION"):
        os.environ.pop(k, None)
    os.environ.update(env)
    import app.config, app.ratelimit, app.api.manage
    for m in (app.config, app.ratelimit, app.api.manage):     # config primeiro, depois quem o usa
        importlib.reload(m)
    if "main" in sys.modules:
        return importlib.reload(sys.modules["main"])
    return importlib.import_module("main")


with tempfile.TemporaryDirectory() as tmp:
    from fastapi.testclient import TestClient

    # 1) produção com segredos de exemplo → não sobe
    try:
        fresh({"APP_ENV": "production"}).create_app(Path(tmp) / "a.db", Path(tmp) / "d")
        check(False, "deveria recusar segredos de exemplo")
    except RuntimeError as e:
        check("insegura" in str(e), "produção recusa subir com segredos de exemplo")

    good = {"APP_ENV": "production", "QR_SECRET": "q" * 40, "AUTH_SECRET": "a" * 40}
    main = fresh(good)
    c = TestClient(main.create_app(Path(tmp) / "p.db", Path(tmp) / "d"))
    check(c.get("/docs").status_code == 404 and c.get("/health").json() == {"ok": True}, "/docs escondido, /health ok")
    check(c.post("/v1/auth/register", json={"email": "p@x.com", "name": "Prof", "password": "senha-forte-1"}).status_code == 201,
          "cadastro aberto enquanto ALLOW_REGISTRATION=true")
    codes = [c.post("/v1/auth/login", json={"email": "p@x.com", "password": "errada"}).status_code for _ in range(11)]
    check(codes[:10] == [401] * 10 and codes[10] == 429, "11ª tentativa de senha errada → 429")
    check(c.post("/v1/auth/login", json={"email": "outro@x.com", "password": "x"}).status_code == 401,
          "limite é por e-mail+IP (outro e-mail continua podendo tentar)")

    main = fresh({**good, "ALLOW_REGISTRATION": "false"})
    c = TestClient(main.create_app(Path(tmp) / "p.db", Path(tmp) / "d"))
    r = c.post("/v1/auth/register", json={"email": "z@x.com", "name": "Zé", "password": "senha-forte-1"})
    check(r.status_code == 403 and "fechado" in r.json()["detail"], "ALLOW_REGISTRATION=false fecha o cadastro")
    check(c.post("/v1/auth/login", json={"email": "p@x.com", "password": "senha-forte-1"}).status_code == 200,
          "conta existente continua entrando")

    # 2) backup e restauração
    fresh({})
    from app.backup import make_backup, restore
    data = Path(tmp) / "d"
    (data / "assets" / "e1").mkdir(parents=True, exist_ok=True)
    (data / "assets" / "e1" / "img.png").write_bytes(b"png")
    for _ in range(3):
        z = make_backup(Path(tmp) / "p.db", data, keep=2)
    check(len(list((data / "backups").glob("*.zip"))) <= 2, "mantém só os N backups mais recentes")
    names = zipfile.ZipFile(z).namelist()
    check("exam.db" in names and "assets/e1/img.png" in names, "backup tem banco + imagens")
    snap = Path(tmp) / "check.db"
    snap.write_bytes(zipfile.ZipFile(z).read("exam.db"))
    n = sqlite3.connect(snap).execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    check(n == 1, "banco do backup íntegro (1 professor)")
    (Path(tmp) / "p.db").unlink()
    (data / "assets" / "e1" / "img.png").unlink()
    restore(z, data, Path(tmp) / "p.db")
    check((Path(tmp) / "p.db").exists() and (data / "assets" / "e1" / "img.png").read_bytes() == b"png", "restauração devolve banco e imagens")
print("\nPRODUÇÃO OK")
