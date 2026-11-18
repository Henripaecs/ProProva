"""Roda em PROCESSO SEPARADO (evita conflito do Playwright com o loop do uvicorn, sobretudo no Windows).

  python -m app.sheet.pdf_worker entrada.html saida.pdf          → cartão-resposta (margem zero)
  python -m app.sheet.pdf_worker --jobs jobs.json                → lote: um só Chromium para N arquivos

jobs.json = [{"html": "...", "pdf": "...", "kind": "sheet" | "booklet", "footer": "texto do rodapé"}]
"""
import html
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_FOOTER = ('<div style="width:100%;font-size:8px;font-family:Arial,sans-serif;color:#444;'
           'padding:0 14mm;display:flex;justify-content:space-between">'
           '<span>{label}</span><span>Página <span class="pageNumber"></span> de '
           '<span class="totalPages"></span></span></div>')


def _render(page, job: dict) -> None:
    page.goto(Path(job["html"]).resolve().as_uri(), wait_until="load")
    if job.get("kind") == "booklet":
        page.pdf(path=job["pdf"], width="210mm", height="297mm", print_background=True,
                 prefer_css_page_size=True, display_header_footer=True,
                 header_template="<div></div>",
                 footer_template=_FOOTER.format(label=html.escape(job.get("footer", ""))),
                 margin={"top": "14mm", "right": "14mm", "bottom": "16mm", "left": "14mm"})
    else:                                   # cartão: margem zero e nada de cabeçalho/rodapé
        page.pdf(path=job["pdf"], width="210mm", height="297mm", print_background=True,
                 prefer_css_page_size=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})


def run(jobs: list[dict]) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            for job in jobs:
                _render(page, job)
        finally:
            browser.close()


if __name__ == "__main__":
    if sys.argv[1] == "--jobs":
        run(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    else:
        run([{"html": sys.argv[1], "pdf": sys.argv[2], "kind": "sheet"}])
