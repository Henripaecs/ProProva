# ProProva — Criação de provas e correção automática por foto

Projeto independente, 100% local (sem APIs de IA externas).

```
answer_sheet/   templates: cartão-resposta (geometria fixa) e caderno da prova (estilo livre)
backend/        FastAPI + OpenCV + SQLite (dev)
  app/omr/      layout, QR assinado, alinhamento, correção, revisão humana
  app/sheet/    PDF do cartão, do caderno e da turma inteira (Chromium via Playwright + pypdf)
  app/exam_content.py   modelo do editor: questões, alternativas, imagens, estilo → gabarito
  app/db/       SqliteRepo (troque por PostgresRepo em produção)
  app/api/      scan.py (correção) · exams.py (editor, imagens, impressão, CSV) · manage.py (login, turmas, alunos, notas)
web/            painel do professor (Next.js)
servidor-pc/    rodar no seu PC (Windows) e publicar na internet de graça com Tailscale — ver servidor-pc/LEIA-ME.md
deploy/         alternativa: servidor Linux na nuvem com Docker Compose + Caddy (HTTPS) — ver deploy/README.md
mobile/         app ProProva (Flutter): painel dentro do app + câmera de correção
database/       schema_sqlite.sql (dev) e schema.sql (PostgreSQL, produção)
tools/          make_sample_sheet.py, run_photos.py, live_detector_reference.py
tests/          synthetic_roundtrip, test_api_flow, test_pdf_geometry, test_exam_pdf
```

## Rodando tudo (desenvolvimento)
Três terminais:
```powershell
# 1) API
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 2) Painel web  →  http://localhost:3000
cd web
npm install
npm run dev

# 3) App (ver mobile/README.md)
cd mobile
python setup_platforms.py
flutter run
```

## Instalação (Windows PowerShell)
```powershell
cd backend
pip install -r requirements.txt
python -m playwright install chromium      # necessário para gerar o PDF do cartão
```
No Linux/Mac é igual; só muda a forma de definir variáveis (`export QR_SECRET=...`).

## Testes automáticos (rode de dentro de `backend`)
```powershell
pip install httpx                           # só para o teste da API
python ../tests/synthetic_roundtrip.py      # leitura com perspectiva, rotação, sombra → PASSOU
python ../tests/test_api_flow.py            # login → prova → cartão → scan → revisão → nota → TUDO OK
python ../tests/test_pdf_geometry.py        # PDF real bate com a geometria do leitor → PDF OK
python ../tests/test_exam_pdf.py            # editor → caderno + cartão → PDF da turma → versões → PROVA EM PDF OK
python ../tests/test_production.py          # segredos, cadastro fechado, limite de senha, backup → PRODUÇÃO OK
python ../tests/test_exam_features.py       # logo, títulos de seção, imagens nas alternativas → RECURSOS DO CADERNO OK
```

## PRIORIDADE 1 — validar com papel real (faça antes de tudo)
Da pasta raiz do projeto:
```powershell
python tools/make_sample_sheet.py           # gera samples/cartao_teste.pdf + gabarito_teste.json
```
1. Imprima o PDF em **escala 100%** (nunca "ajustar à página"), preferencialmente em impressora comum.
2. Preencha seguindo o gabarito indicado: padrão A,B,C… , questões em branco e duplas marcações propositais.
   Faça versões com **caneta azul/preta, lápis e preenchimento fraco**.
3. Fotografe com o celular em várias condições e copie para uma pasta `fotos/`:
   luz boa · sombra no meio da folha · luz amarela · ângulo forte (~30°) · folha levemente dobrada · cartão girado/de cabeça para baixo · levemente desfocada.
4. Rode:
```powershell
python tools/run_photos.py fotos --gabarito samples/gabarito_teste.json
```
Para cada foto: falha com dica (ex.: "foto escura") ou acertos X/50 e a lista de erros.
Abra `debug/<foto>_roi.jpg` (bolhas coloridas por status) e `debug/<foto>_fills.csv` (valores medidos)
para calibrar `GraderConfig` em `app/omr/grader.py` e `SHARPNESS_MIN` em `app/omr/preprocess.py`.
Meta: **0 erros silenciosos** (resposta errada lida com confiança); incerteza deve cair em "revisão".

## Rodar a API
```powershell
$env:QR_SECRET  = "troque-por-um-segredo-longo"
$env:AUTH_SECRET = "outro-segredo-longo"
python -m uvicorn main:app --reload
```
Abra http://127.0.0.1:8000/docs → `POST /v1/auth/register` → botão **Authorize** (cole o token).
Fluxo: criar turma → aluno → prova (com gabarito) → `GET /v1/exams/{id}/sheets/{aluno}` (PDF do cartão)
→ `POST /v1/scan` (foto) → se houver rasuras: `GET /v1/scans/{id}/answers/{n}/crop.png` e
`PUT /v1/scans/{id}/answers/{n}` (professor decide) → `GET /v1/exams/{id}/results`.

IMPORTANTE: use os **mesmos** `QR_SECRET` ao gerar o cartão e ao corrigir; senão o QR é rejeitado.

## Prova completa em PDF
O editor guarda o **conteúdo** e o **estilo** do caderno. O conteúdo inclui questões, alternativas (texto, imagem ou os dois), imagens, títulos de seção como "Matemática" (com texto de apoio opcional) e a logo da escola (opcional, com a opção de mostrar ou não). O estilo cobre fonte, tamanho,
1 ou 2 colunas, espaçamento, alternativas em linha ou em coluna. O gabarito, o número de questões e de
alternativas saem do próprio conteúdo, então caderno e cartão nunca discordam.

Texto com marcação simples: `**negrito**`, `*itálico*`, `__sublinhado__`, `x^2^`, `H~2~O`. O HTML digitado
é sempre escapado.

O caderno e o cartão são renderizados como documentos separados e só depois unidos. Assim o estilo do
caderno nunca desloca uma bolha. Por turma:
- `GET /v1/exams/{id}/classes/{turma}/print` → um PDF com a turma inteira (caderno com o nome do aluno + cartão dele);
- `?layout=zip` → um PDF por aluno · `?duplex=true` → o cartão começa sempre numa folha nova ·
  `?include_booklet=false` → só cartões;
- um Chromium só para a turma toda (medido: 30 alunos, 150 páginas, ≈ 5 s).

**Versões:** a 1ª impressão trava a versão. Salvar depois disso cria a versão seguinte, e os cartões já
impressos continuam sendo corrigidos pelo gabarito da versão deles (o QR leva o número da versão).

## Ajustes no motor (validação com as 6 fotos reais)
- Bolhas preenchidas eram confundidas com os marcadores (um círculo tem "extensão" 0,785, logo acima do corte
  de 0,78). Agora o detector exige circularidade de quadrado e polígono de 4 vértices, e escolhe os candidatos
  por área.
- Leitor de QR principal passou a ser o zxing-cpp (o OpenCV fica de reserva). Ele lê QR pequenos, de fotos
  tiradas de longe, que o OpenCV perdia.
- Se um canto estiver cortado na foto, a resposta agora é `markers_not_found` com a dica "enquadre a folha
  inteira", e não mais um erro enganoso de QR.

Resultado: 5 de 6 fotos com 50/50 e nenhum erro silencioso. A 6ª tem um marcador cortado pela borda da
foto e é recusada com a dica certa.

## Servidor na internet
- **No seu PC (grátis, sem cartão):** `servidor-pc/LEIA-ME.md`. São scripts de dois cliques, e o Tailscale Funnel dá o endereço HTTPS.
- **Na nuvem (Linux + Docker):** `deploy/README.md` (ex.: Oracle Cloud, que pede CNPJ para conta de empresa).

Nos dois casos o painel repassa `/v1` para a API, então painel e app usam **um endereço só**. Em produção (`APP_ENV=production`):
- a API recusa subir com os segredos de exemplo;
- `ALLOW_REGISTRATION=false` fecha o cadastro de contas novas;
- 10 senhas erradas em 15 min bloqueiam o login daquele e-mail;
- o `/docs` fica desligado;
- `python -m app.backup` gera backup (banco + imagens + recortes) e `--restore` restaura.

## Próximos passos (produção)
PostgresRepo · armazenamento das fotos/recortes em object storage · política de retenção
(`SqliteRepo.purge_scans_before` já apaga correções antigas e recortes) · limites de envio · HTTPS e deploy.
