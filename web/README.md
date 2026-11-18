# Painel do professor (Next.js)

```powershell
cd web
copy .env.example .env.local      # (Linux/Mac: cp) — ajuste NEXT_PUBLIC_API_URL se a API não estiver em 127.0.0.1:8000
npm install
npm run dev                       # http://localhost:3000
```
Produção: veja `deploy/README.md` (Docker + HTTPS). Lá o painel e a API ficam no mesmo endereço.

Telas:
- **Provas**: lista, nova prova (completa ou só cartão), editor com questões, alternativas, imagem, peso,
  anulação, várias corretas, negrito/itálico/sub/sobrescrito, fonte/colunas/espaçamento e pré-visualização.
- **Prova**: imprimir para uma turma (PDF único ou ZIP, com ou sem caderno, frente e verso), média,
  quem falta corrigir, notas, exportar CSV.
- **Revisão**: recorte da linha da foto ao lado dos botões A–E e "Sem resposta"; nota recalculada na hora;
  grade com todas as respostas (clique corrige qualquer leitura).
- **Turmas**: cadastro de alunos um a um ou colando a lista (Nome;Matrícula, ou duas colunas do Excel).
- **Corrigir por foto**: arraste várias fotos; cada cartão é identificado pelo QR.

O token fica no navegador (expira em 12 h). A API precisa liberar a origem do painel em `CORS_ORIGINS`
(padrão: `http://localhost:3000,http://127.0.0.1:3000`).
