"""
Gera um cartão-resposta de TESTE para você imprimir, preencher à mão e fotografar.

  python tools/make_sample_sheet.py                 (rode a partir da pasta do projeto)
  python tools/make_sample_sheet.py --questions 30 --columns 3

Saídas em ./samples:
  cartao_teste.pdf      (ou .html se o Chromium não estiver instalado)
  gabarito_teste.json   padrão de preenchimento e rasuras que você deve fazer
"""
import argparse, json, sys, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config
from app.omr.layout import AnswerGridSpec
from app.sheet.render import PdfRenderError, render_answer_sheet_html, render_pdf_sync


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=int, default=50)
    ap.add_argument("--options", type=int, default=5)
    ap.add_argument("--columns", type=int, default=4)
    ap.add_argument("--out", default="samples")
    a = ap.parse_args()

    spec = AnswerGridSpec(a.questions, a.options, a.columns)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    html = render_answer_sheet_html(spec, exam_id=uuid.uuid4(), student_id=uuid.uuid4(), version=1,
                                    exam_title="Cartão de TESTE", student_name="Aluno Exemplo",
                                    class_name="Turma Teste", qr_secret=config.QR_SECRET)
    (out / "cartao_teste.html").write_text(html, encoding="utf-8")
    try:
        (out / "cartao_teste.pdf").write_bytes(render_pdf_sync(html))
        print("PDF gerado:", out / "cartao_teste.pdf")
    except PdfRenderError as exc:
        print("Sem PDF automático (", str(exc)[:120], ")\n"
              "→ Instale com:  python -m playwright install chromium\n"
              "→ ou abra samples/cartao_teste.html no Chrome e imprima/salve como PDF "
              "(margens: nenhuma, escala: 100%, sem cabeçalho/rodapé).")

    # Protocolo de preenchimento: padrão A,B,C,D,E…; brancos e rasuras propositais.
    blanks = [q for q in range(7, a.questions + 1, 10)]
    double = [q for q in range(10, a.questions + 1, 10)]
    answers = {str(q): None if q in blanks else spec.options[(q - 1) % a.options] for q in range(1, a.questions + 1)}
    for q in double:
        answers[str(q)] = None
    (out / "gabarito_teste.json").write_text(json.dumps(
        {"answers": answers, "expect_review": double, "blank": blanks}, indent=2), encoding="utf-8")
    print(f"\nPreencha assim: questão N → alternativa (N-1) mod {a.options} (1=A, 2=B, 3=C…)."
          f"\n  Deixe em BRANCO: {blanks}"
          f"\n  Marque DUAS alternativas (rasura): {double}"
          f"\nGabarito salvo em {out / 'gabarito_teste.json'}")


if __name__ == "__main__":
    main()
