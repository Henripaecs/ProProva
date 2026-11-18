# API (FastAPI + OpenCV + Chromium para os PDFs). Contexto do build = raiz do projeto.
# Funciona em x86-64 e em ARM64 (ex.: Oracle Cloud Ampere).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install -r requirements.txt \
 && python -m playwright install --with-deps chromium \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# código + templates do cartão/caderno + schema do banco (o código procura ../answer_sheet e ../database)
COPY answer_sheet /app/answer_sheet
COPY database /app/database
COPY backend /app/backend

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown -R app /data
USER app
ENV APP_ENV=production DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# 1 worker: SQLite + limite de tentativas em memória. Um servidor de 2 núcleos atende uma escola com folga.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
