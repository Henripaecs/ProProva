"""Fluxo completo da API em SQLite temporário. Rode:  cd backend && python ../tests/test_api_flow.py"""
import sys, tempfile
from pathlib import Path
from uuid import UUID

import cv2
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config
from app.omr.layout import AnswerGridSpec
from app.omr.qr import SheetPayload, encode_payload
from main import create_app
from synthetic_roundtrip import draw_sheet, simulate_photo


def check(cond, msg):
    print(("  ok  " if cond else " FAIL ") + msg)
    if not cond:
        sys.exit(1)


with tempfile.TemporaryDirectory() as tmp:
    client = TestClient(create_app(Path(tmp) / "t.db", Path(tmp) / "data"))
    H = lambda tok: {"Authorization": f"Bearer {tok}"}

    tok = client.post("/v1/auth/register", json={"email": "prof@x.com", "name": "Prof", "password": "senha-forte-1"}).json()["token"]
    check(client.post("/v1/auth/register", json={"email": "prof@x.com", "name": "Prof", "password": "senha-forte-1"}).status_code == 409, "e-mail duplicado → 409")
    check(client.post("/v1/auth/login", json={"email": "prof@x.com", "password": "errada"}).status_code == 401, "senha errada → 401")
    tok = client.post("/v1/auth/login", json={"email": "prof@x.com", "password": "senha-forte-1"}).json()["token"]

    cid = client.post("/v1/classes", json={"name": "9A"}, headers=H(tok)).json()["id"]
    sid = client.post(f"/v1/classes/{cid}/students", json={"name": "Maria Silva", "enrollment": "001"}, headers=H(tok)).json()["id"]

    spec = AnswerGridSpec(50)
    key = {q: spec.options[(q - 1) % 5] for q in range(1, 51)}
    key[5] = None                                                    # anulada
    r = client.post("/v1/exams", json={"title": "Prova 1", "n_questions": 50, "answer_key": key}, headers=H(tok))
    check(r.status_code == 201, "prova criada")
    eid = r.json()["id"]
    check(client.post("/v1/exams", json={"title": "x", "n_questions": 50, "answer_key": {"1": "A"}}, headers=H(tok)).status_code == 422, "gabarito incompleto → 422")

    html = client.get(f"/v1/exams/{eid}/sheets/{sid}?format=html", headers=H(tok))
    check(html.status_code == 200 and html.text.count('class="bubble"') == 250, "cartão HTML gerado (250 bolhas)")

    # aluno erra q3 e q4, marca duas alternativas na q20
    answers = {q: a for q, a in key.items() if a}
    answers[3], answers[4] = "E", "E"
    qr = encode_payload(SheetPayload(UUID(eid), UUID(sid), 1), config.QR_SECRET)
    sheet = draw_sheet(spec, qr, answers)
    import numpy as np
    for letter in ("A", "C"):
        cx, cy = (int(v * 8) for v in spec.bubble_center_mm(19, spec.options.index(letter)))
        cv2.circle(sheet, (cx, cy), int(spec.bubble_radius_px * .92), (70, 60, 50), -1, cv2.LINE_AA)
    photo = cv2.imencode(".jpg", simulate_photo(sheet), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()

    check(client.post("/v1/scan", files={"file": ("f.jpg", photo, "image/jpeg")}).status_code == 401, "scan sem login → 401")
    r = client.post("/v1/scan", files={"file": ("f.jpg", photo, "image/jpeg")}, headers=H(tok))
    check(r.status_code == 200, f"scan ok ({r.status_code}) {r.text[:300]}")
    body = r.json()
    check(body["review_needed"] == [20], f"só a q20 pede revisão: {body['review_needed']}")
    check(body["score"]["pending"] == 1 and body["score"]["wrong"] == 2, "nota parcial: 2 erradas, 1 pendente")

    scan_id = body["scan_id"]
    c = client.get(f"/v1/scans/{scan_id}/answers/20/crop.png", headers=H(tok))
    check(c.status_code == 200 and c.content[:4] == b"\x89PNG", "recorte da q20 disponível")

    tok2 = client.post("/v1/auth/register", json={"email": "outro@x.com", "name": "Outro", "password": "senha-forte-2"}).json()["token"]
    check(client.get(f"/v1/scans/{scan_id}/answers/20/crop.png", headers=H(tok2)).status_code == 403, "outro professor → 403")

    check(client.put(f"/v1/scans/{scan_id}/answers/20", json={"answer": "Z"}, headers=H(tok)).status_code == 422, "alternativa inválida → 422")
    r = client.put(f"/v1/scans/{scan_id}/answers/20", json={"answer": key[20]}, headers=H(tok)).json()
    check(r["review_needed"] == [] and r["score"]["pending"] == 0, "revisão aplicada")
    check(r["score"]["points"] == 48 and r["score"]["max_points"] == 50, f"nota final 48/50 (veio {r['score']['points']})")

    res = client.get(f"/v1/exams/{eid}/results", headers=H(tok)).json()
    check(len(res) == 1 and res[0]["student_name"] == "Maria Silva" and res[0]["score"]["points"] == 48, "lista de resultados")
print("\nTUDO OK")
