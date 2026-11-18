from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api import exams, manage, scan
from app.db.sqlite_repo import SqliteRepo


def create_app(db_path: Path | str | None = None, data_dir: Path | str | None = None) -> FastAPI:
    config.check_production()
    repo = SqliteRepo(db_path or config.DB_PATH, data_dir or config.DATA_DIR)
    app = FastAPI(title="ProProva API",
                  docs_url=None if config.IS_PRODUCTION else "/docs",      # sem /docs público em produção
                  redoc_url=None, openapi_url=None if config.IS_PRODUCTION else "/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition", "X-Exam-Version"])
    scan.register_error_handlers(app)
    app.dependency_overrides[scan.get_repo] = lambda: repo
    app.include_router(manage.router, prefix="/v1")
    app.include_router(exams.router, prefix="/v1")
    app.include_router(scan.router, prefix="/v1")

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"ok": True}

    return app


app = create_app()
