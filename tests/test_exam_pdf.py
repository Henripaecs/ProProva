"""
Prova completa (editor → caderno + cartão → PDF por turma) e travamento de versão.
Rode:  cd backend && python ../tests/test_exam_pdf.py
Precisa do Chromium do Playwright (python -m playwright install chromium).
"""
import io, sys, tempfile, zipfile
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
import pypdfium2 as pdfium
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config
from app.omr.grader import grade_roi
from app.omr.layout import CANVAS_H_PX, CANVAS_W_PX, PPMM, AnswerGridSpec
from app.omr.qr import SheetPayload, decode_payload, encode_payload
from app.omr.sheet_aligner import align_sheet
from main import create_app
from synthetic_roundtrip import draw_sheet, simulate_photo


def check(cond, msg):
    print(("  ok  " if cond else " FAIL ") + msg)
    if not cond:
        sys.exit(1)


def page_bgr(pdf: pdfium.PdfDocument, i: int) -> np.ndarray:
    img = np.array(pdf[i].render(scale=PPMM / (72 / 25.4)).to_pil().convert("RGB"))[:, :, ::-1]
    return cv2.resize(img, (CANVAS_W_PX, CANVAS_H_PX), interpolation=cv2.INTER_AREA)


def is_answer_sheet(bgr: np.ndarray) -> str | None:
    try:
        return align_sheet(bgr).qr_text
    except Exception:
        return None


QUESTIONS = [
    {"stem": "Quanto é **2 + 2**?", "options": ["3", "4", "5", "22"], "correct": "B"},
    {"stem": "A fórmula da água é H~2~O e a área do quadrado é l^2^.", "options": ["Verdadeiro", "Falso"], "correct": "A"},
    {"stem": "Observe a figura e marque a cor predominante.", "options": ["Azul", "Vermelho", "Verde", "Preto", "Branco"],
     "correct": "A", "image_width": 50},
    {"stem": "Questão anulada pela coordenação.", "options": ["a", "b", "c", "d", "e"], "correct": None},
    {"stem": "Vale o dobro: <script>alert(1)</script> *itálico* __sublinhado__",
     "options": ["um", "dois", "três", "quatro", "cinco"], "correct": "E", "weight": 2},
] + [{"stem": f"Pergunta {i} — texto mais longo para ocupar espaço na coluna e forçar a quebra de página "
              f"do caderno. " * 3, "options": [f"Alternativa {l}" for l in "ABCDE"], "correct": "ABCDE"[i % 5]}
     for i in range(6, 31)]

with tempfile.TemporaryDirectory() as tmp:
    client = TestClient(create_app(Path(tmp) / "t.db", Path(tmp) / "data"))
    tok = client.post("/v1/auth/register", json={"email": "p@x.com", "name": "Prof", "password": "senha-forte-1"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    cid = client.post("/v1/classes", json={"name": "9º A"}, headers=H).json()["id"]
    r = client.post(f"/v1/classes/{cid}/students/bulk", headers=H, json={"students": [
        {"name": "Ana Souza", "enrollment": "1"}, {"name": "Bruno Lima", "enrollment": "2"},
        {"name": "Cássia Ribeiro", "enrollment": "3"}, {"name": "Repetida", "enrollment": "3"}]}).json()
    check(len(r["created"]) == 3 and r["skipped"] == ["Repetida"], "cadastro em lote (matrícula repetida pulada)")
    students = client.get(f"/v1/classes/{cid}", headers=H).json()["students"]

    content = {"header": {"school": "Escola Estadual Exemplo", "subtitle": "Matemática — 2º bimestre",
                          "instructions": "Leia com **atenção**.\nUse caneta azul ou preta."},
               "questions": [dict(q) for q in QUESTIONS]}
    style = {"font_family": "serif", "font_size_pt": 11, "columns": 2, "show_points": True}
    q3_no_img = content["questions"][2]
    r = client.post("/v1/exams", json={"title": "Avaliação Bimestral", "content": content, "style": style}, headers=H)
    check(r.status_code == 201, f"prova criada a partir do editor ({r.status_code} {r.text[:200]})")
    eid = r.json()["id"]
    exam = client.get(f"/v1/exams/{eid}", headers=H).json()
    check(exam["grid_spec"]["n_questions"] == 30 and exam["grid_spec"]["n_options"] == 5, "cartão derivado: 30 questões × 5")
    check(exam["answer_key"]["1"] == "B" and exam["answer_key"]["4"] is None and exam["weights"] == {"5": 2.0},
          "gabarito, anulada e peso derivados do conteúdo")

    bad = {**content, "questions": [{"stem": "x", "options": ["a", "b"], "correct": "C"}]}
    check(client.put(f"/v1/exams/{eid}", json={"title": "x", "content": bad}, headers=H).status_code == 422,
          "resposta correta fora das alternativas → 422")

    # imagem: gera um PNG azul, envia e anexa à questão 3
    png = cv2.imencode(".png", np.full((300, 500, 3), (200, 80, 20), np.uint8))[1].tobytes()
    a = client.post(f"/v1/exams/{eid}/assets", files={"file": ("fig.png", png, "image/png")}, headers=H)
    check(a.status_code == 201, "imagem enviada")
    check(client.post(f"/v1/exams/{eid}/assets", files={"file": ("x.png", b"not an image", "image/png")},
                      headers=H).status_code == 422, "arquivo que não é imagem → 422")
    content["questions"][2] = {**q3_no_img, "image": a.json()["id"]}
    r = client.put(f"/v1/exams/{eid}", json={"title": "Avaliação Bimestral", "content": content, "style": style}, headers=H)
    check(r.status_code == 200 and r.json() == {"version": 1, "new_version": False, "columns": 4},
          "salvar rascunho não cria versão nova")

    html = client.get(f"/v1/exams/{eid}/booklet?format=html", headers=H).text
    check("<b>2 + 2</b>" in html and "H<sub>2</sub>O" in html and "l<sup>2</sup>" in html, "negrito/sub/sobrescrito")
    check("<script>" not in html and "&lt;script&gt;" in html, "HTML digitado é escapado (sem injeção)")
    check("data:image/png;base64," in html and "(2,0 pts)" in html, "imagem embutida e pontuação exibida")

    prev = client.get(f"/v1/exams/{eid}/booklet", headers=H)
    check(prev.status_code == 200 and prev.content[:4] == b"%PDF", "pré-visualização do caderno em PDF")
    n_booklet = len(pdfium.PdfDocument(prev.content))
    check(n_booklet >= 2, f"caderno com {n_booklet} páginas")

    # ── PDF da turma ─────────────────────────────────────────────────────────
    r = client.get(f"/v1/exams/{eid}/classes/{cid}/print", headers=H)
    check(r.status_code == 200 and r.headers["content-type"] == "application/pdf", "PDF único da turma")
    pdf = pdfium.PdfDocument(r.content)
    check(len(pdf) == 3 * (n_booklet + 1), f"{len(pdf)} páginas = 3 alunos × ({n_booklet} do caderno + 1 cartão)")
    for i, st in enumerate(students):
        last = (i + 1) * (n_booklet + 1) - 1
        qr = is_answer_sheet(page_bgr(pdf, last))
        check(qr is not None, f"página {last + 1} é o cartão de {st['name']}")
        p = decode_payload(qr, config.QR_SECRET)
        check(p.student_id == UUID(st["id"]) and p.exam_id == UUID(eid) and p.version == 1, "  QR aponta para o aluno certo")
        check(is_answer_sheet(page_bgr(pdf, last - 1)) is None, "  página anterior é caderno, não cartão")
        text = pdf[last - n_booklet].get_textpage().get_text_range()
        check(st["name"] in text and "ESCOLA ESTADUAL EXEMPLO" in text, "  caderno personalizado com o nome")
        roi = align_sheet(page_bgr(pdf, last)).roi
        check(all(x.status.value == "blank" for x in grade_roi(roi, AnswerGridSpec.from_json(exam["grid_spec"]))),
              "  cartão impresso lido: 30 em branco")

    r = client.get(f"/v1/exams/{eid}/classes/{cid}/print?duplex=true", headers=H)
    n = len(pdfium.PdfDocument(r.content))
    per = n // 3
    check(n % 3 == 0 and per % 2 == 0, f"frente e verso: {per} páginas por aluno (par)")

    r = client.get(f"/v1/exams/{eid}/classes/{cid}/print?layout=zip&include_booklet=false", headers=H)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(zf.namelist())
    check(names == ["01_Ana_Souza.pdf", "02_Bruno_Lima.pdf", "03_Cassia_Ribeiro.pdf"], f"ZIP por aluno: {names}")
    check(all(len(pdfium.PdfDocument(zf.read(nm))) == 1 for nm in names), "  só cartão = 1 página cada")

    r = client.get(f"/v1/exams/{eid}/classes/{cid}/students/{students[0]['id']}/print", headers=H)
    check(len(pdfium.PdfDocument(r.content)) == n_booklet + 1, "PDF individual de um aluno")

    # ── versão travada após imprimir ─────────────────────────────────────────
    check(client.get(f"/v1/exams/{eid}", headers=H).json()["locked"], "versão 1 travada após impressão")
    content["questions"][0]["correct"] = "C"                       # professor muda o gabarito depois
    r = client.put(f"/v1/exams/{eid}", json={"title": "Avaliação Bimestral", "content": content, "style": style}, headers=H).json()
    check(r["version"] == 2 and r["new_version"], "editar prova impressa cria a versão 2")

    # Ana responde o cartão v1: q1=B (certo no v1), resto em branco → v1 continua corrigindo pelo gabarito v1
    spec = AnswerGridSpec.from_json(exam["grid_spec"])
    qr = encode_payload(SheetPayload(UUID(eid), UUID(students[0]["id"]), 1), config.QR_SECRET)
    photo = cv2.imencode(".jpg", simulate_photo(draw_sheet(spec, qr, {1: "B", 5: "E"})))[1].tobytes()
    s = client.post("/v1/scan", files={"file": ("f.jpg", photo, "image/jpeg")}, headers=H).json()
    # v1: q1 certa (1) + q4 anulada (1) + q5 peso 2 certa (2) = 4 de 31
    check(s["score"]["points"] == 4 and s["score"]["max_points"] == 31, f"cartão v1 corrigido pelo gabarito v1 ({s['score']['points']}/{s['score']['max_points']})")

    d = client.get(f"/v1/scans/{s['scan_id']}", headers=H).json()
    check(d["student_name"] == "Ana Souza" and d["exam_title"] == "Avaliação Bimestral" and len(d["answers"]) == 30,
          "detalhe do scan para a tela de revisão")

    csv_txt = client.get(f"/v1/exams/{eid}/results.csv", headers=H).content.decode("utf-8-sig")
    check(csv_txt.splitlines()[1].startswith("Ana Souza;4,00;31,00;"), "notas em CSV (Excel pt-BR)")

    lst = client.get("/v1/exams", headers=H).json()
    check(lst[0]["version"] == 2 and lst[0]["has_booklet"] and lst[0]["n_scans"] == 1, "lista de provas")

    tok2 = client.post("/v1/auth/register", json={"email": "o@x.com", "name": "Outro", "password": "senha-forte-2"}).json()["token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    check(client.get(f"/v1/exams/{eid}/classes/{cid}/print", headers=H2).status_code == 404, "outro professor não imprime")
    check(client.get(f"/v1/exams/{eid}/assets/{a.json()['id']}", headers=H2).status_code == 404, "nem vê as imagens")

    check(client.delete(f"/v1/students/{students[0]['id']}", headers=H).status_code == 204, "aluno excluído (LGPD)")
    check(client.get(f"/v1/exams/{eid}/results", headers=H).json() == [], "  e a correção dele junto")
    check(client.delete(f"/v1/exams/{eid}", headers=H).status_code == 204, "prova excluída")
    check(not list((Path(tmp) / "data" / "assets").rglob("*.png")), "  imagens apagadas do disco")
print("\nPROVA EM PDF OK")
