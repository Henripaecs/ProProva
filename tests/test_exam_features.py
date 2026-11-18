"""
Logo da escola (opcional), títulos de seção e imagens nas alternativas.
Rode:  cd backend && python ../tests/test_exam_features.py   (gera /tmp/caderno_recursos.pdf para conferir)
"""
import sys, tempfile
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from main import create_app


def check(cond, msg):
    print(("  ok  " if cond else " FAIL ") + msg)
    if not cond:
        sys.exit(1)


def png(draw) -> bytes:
    img = np.full((300, 300, 3), 255, np.uint8)
    draw(img)
    return cv2.imencode(".png", img)[1].tobytes()


LOGO = png(lambda im: (cv2.rectangle(im, (20, 60), (280, 240), (150, 60, 20), -1),
                       cv2.putText(im, "ESCOLA", (40, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4)))
BOLA = png(lambda im: (cv2.circle(im, (150, 150), 120, (30, 120, 230), -1),
                       cv2.circle(im, (150, 150), 120, (0, 0, 0), 4)))
GRAFICO = png(lambda im: [cv2.rectangle(im, (30 + i * 60, 270 - h), (70 + i * 60, 270), (60, 140, 40), -1)
                          for i, h in enumerate((80, 150, 110, 220))])

with tempfile.TemporaryDirectory() as tmp:
    c = TestClient(create_app(Path(tmp) / "t.db", Path(tmp) / "d"))
    H = {"Authorization": "Bearer " + c.post("/v1/auth/register", json={
        "email": "p@x.com", "name": "Prof", "password": "senha-forte-1"}).json()["token"]}

    base_q = lambda stem, correct="A": {"stem": stem, "options": ["um", "dois", "três", "quatro"], "correct": correct}
    content = {"header": {"school": "Escola Municipal Exemplo", "subtitle": "Avaliação integrada — 2º bimestre"},
               "questions": [base_q("Qual palavra é um substantivo?") for _ in range(2)] + [base_q("Quanto é 2 + 3?")]}
    eid = c.post("/v1/exams", json={"title": "Avaliação Integrada", "content": content}, headers=H).json()["id"]
    up = lambda name, data: c.post(f"/v1/exams/{eid}/assets", files={"file": (name, data, "image/png")}, headers=H).json()["id"]
    logo, bola, grafico = up("logo.png", LOGO), up("bola.png", BOLA), up("grafico.png", GRAFICO)

    # seções: "Português" antes da 1ª, "Matemática" (com texto de apoio) antes da 3ª
    content["header"].update(logo=logo, show_logo=True)
    content["questions"][0]["section"] = "Português"
    content["questions"][2].update(section="Matemática", section_text="Use os **dados do gráfico** quando necessário.")
    # imagens nas alternativas: A = bola (só imagem), C = gráfico (imagem + texto)
    content["questions"].append({"stem": "Qual figura representa uma bola?", "options": ["", "Um cubo", "Gráfico de barras", "Nenhuma"],
                                 "option_images": [bola, None, grafico, None], "correct": "A", "section": "Ciências"})
    r = c.put(f"/v1/exams/{eid}", json={"title": "Avaliação Integrada", "content": content}, headers=H)
    check(r.status_code == 200, f"salvar com logo, seções e imagens nas alternativas ({r.status_code} {r.text[:150]})")

    exam = c.get(f"/v1/exams/{eid}", headers=H).json()
    q4 = exam["content"]["questions"][3]
    check(q4["option_images"] == [bola, None, grafico, None] and exam["grid_spec"]["n_questions"] == 4,
          "imagens das alternativas guardadas; cartão continua com 4 questões (seção não vira questão)")
    check(exam["content"]["questions"][0]["option_images"] == [None] * 4, "questões antigas sem imagem ficam com [None…]")

    html = c.get(f"/v1/exams/{eid}/booklet?format=html", headers=H).text
    check(html.count('class="logo"') == 1, "logo no cabeçalho")
    check(html.index(">Português</h2>") < html.index("Qual palavra") and html.index(">Matemática</h2>") < html.index("Quanto é 2 + 3?"),
          "títulos de seção antes das questões certas")
    check("<b>dados do gráfico</b>" in html, "texto de apoio da seção com formatação")
    check(html.count('class="oimg"') == 2, "duas alternativas com imagem")
    check(">4.</span>" in html, "numeração contínua (seções não reiniciam a contagem do cartão)")

    content["header"]["show_logo"] = False
    c.put(f"/v1/exams/{eid}", json={"title": "Avaliação Integrada", "content": content}, headers=H)
    html2 = c.get(f"/v1/exams/{eid}/booklet?format=html", headers=H).text
    check('class="logo"' not in html2 and c.get(f"/v1/exams/{eid}", headers=H).json()["content"]["header"]["logo"] == logo,
          "desmarcar 'mostrar logo' tira do caderno mas guarda a logo")
    content["header"]["show_logo"] = True
    c.put(f"/v1/exams/{eid}", json={"title": "Avaliação Integrada", "content": content}, headers=H)

    bad = {**content, "questions": [{"stem": "x", "options": ["a", ""], "correct": "A"}]}
    r = c.put(f"/v1/exams/{eid}", json={"title": "x", "content": bad}, headers=H)
    check(r.status_code == 422 and "alternativa B está vazia" in r.text, "alternativa sem texto e sem imagem → 422 com mensagem clara")
    bad = {**content, "questions": [{"stem": "x", "options": ["a", "b"], "option_images": ["00000000-0000-0000-0000-000000000000", None], "correct": "A"}]}
    check(c.put(f"/v1/exams/{eid}", json={"title": "x", "content": bad}, headers=H).status_code == 422,
          "imagem de alternativa que não é desta prova → 422")
    bad = {**content, "header": {**content["header"], "logo": "00000000-0000-0000-0000-000000000000"}}
    check(c.put(f"/v1/exams/{eid}", json={"title": "x", "content": bad}, headers=H).status_code == 422,
          "logo que não é desta prova → 422")

    for cols in (2, 1):
        r = c.put(f"/v1/exams/{eid}", json={"title": "Avaliação Integrada", "content": content, "style": {"columns": cols}}, headers=H)
        pdf = c.get(f"/v1/exams/{eid}/booklet", headers=H)
        check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF", f"PDF do caderno com {cols} coluna(s)")
        Path(f"/tmp/caderno_recursos_{cols}col.pdf").write_bytes(pdf.content)
        doc = pdfium.PdfDocument(pdf.content)
        doc[0].render(scale=1.4).to_pil().save(f"/tmp/caderno_recursos_{cols}col.png")
        text = doc[0].get_textpage().get_text_range()
        check("PORTUGUÊS" in text and "MATEMÁTICA" in text and "CIÊNCIAS" in text, "  seções aparecem no PDF")
print("\nRECURSOS DO CADERNO OK")
