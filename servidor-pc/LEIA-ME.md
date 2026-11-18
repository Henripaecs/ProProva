# Servidor no seu PC + endereço na internet (Tailscale) — grátis

O sistema roda no seu computador com Windows. O **Tailscale Funnel** dá a ele um endereço fixo com HTTPS,
do tipo `https://proprova.tail1234.ts.net`. Esse endereço funciona de qualquer lugar: no painel, pelo
navegador, e no app, pelo 4G.

**Regra de ouro:** o PC precisa estar **ligado e sem hibernar** enquanto você usa o sistema.

Só o painel fica exposto na internet. A API escuta apenas dentro do PC e recebe as chamadas por meio
do painel.

---

## 1. Instalar (uma vez)
Antes, **feche** o que você deixava aberto no modo de desenvolvimento (os terminais do `uvicorn` e do
`npm run dev`).

Pré-requisitos (você já tem): **Python 3.11+** (instalado pelo python.org, com "Add python.exe to PATH")
e **Node.js 20+**.

Dê dois cliques em **`1-instalar.bat`**. Ele:
- cria o arquivo `servidor-pc\.env` com dois segredos novos. **Guarde uma cópia dele** em lugar seguro
  (um gerenciador de senhas, por exemplo). Sem ele, os cartões impressos deixam de ser aceitos;
- instala a API e o Chromium (que gera os PDFs);
- instala e monta o painel (leva 1–2 minutos).

> Seus dados atuais (`backend\data\exam.db`) continuam sendo usados: contas, turmas e provas
> permanecem. Só os cartões que você **já imprimiu** param de ser aceitos, porque o segredo do QR mudou.
> Reimprima as provas que ainda vai aplicar.

## 2. Ligar o sistema
Dê dois cliques em **`2-iniciar.bat`**. Em alguns segundos aparece "Sistema no ar". As janelas ficam
escondidas e os registros vão para `servidor-pc\logs\`.

Para desligar: **`3-parar.bat`**.

Teste no próprio PC: http://127.0.0.1:3000

## 3. Instalar o Tailscale (uma vez)
1. Baixe em **tailscale.com/download** (Windows) e instale.
2. Clique no ícone do Tailscale perto do relógio → **Log in**. Entre com sua conta Google (é grátis).
3. Escolha um nome curto para o PC, porque ele vira o endereço: abra **login.tailscale.com/admin/machines**
   → no seu PC, **⋯ → Edit machine name** → por exemplo `proprova`.
   *Decida agora: trocar o nome depois muda o endereço, e você teria de reconfigurar o app.*

## 4. Publicar na internet (uma vez)
Com o sistema ligado (passo 2), dê dois cliques em **`4-publicar.bat`**.
- **Na primeira vez**, o Tailscale mostra um link para habilitar o *Funnel* (e o HTTPS) na sua conta.
  Abra o link, clique em habilitar e rode o `4-publicar.bat` de novo.
- No fim aparece o endereço, algo como **`https://proprova.tail1234.ts.net`**.

Pronto: abra esse endereço em qualquer navegador (até no celular, pelo 4G).
O Funnel fica gravado e continua ativo depois que o PC reinicia; não precisa rodar este passo de novo.

## 5. Criar sua conta e fechar o cadastro
1. No endereço público, clique em **Criar conta** (se você ainda não tem conta).
2. Abra `servidor-pc\.env` no Bloco de Notas e troque `ALLOW_REGISTRATION=true` por **`false`**.
3. Rode **`3-parar.bat`** e depois **`2-iniciar.bat`**.

A partir daí, ninguém mais consegue criar conta no seu sistema, mesmo sabendo o endereço. Para cadastrar
outro professor: volte para `true`, crie a conta, feche de novo.

## 6. App
No app, em **Servidor**, digite o endereço **sem o `https://`**, por exemplo `proprova.tail1234.ts.net`
(o app coloca o HTTPS sozinho). Entre com a mesma conta.

## 7. Deixar ligado sem esforço
- **Não hibernar:** Configurações → Sistema → Energia → *Tela e suspensão* → "Quando conectado à
  energia, colocar o dispositivo em suspensão após": **Nunca**. (A tela pode desligar; isso não atrapalha.)
- **Iniciar junto com o Windows:** aperte `Win + R`, digite `shell:startup` e Enter. Na pasta que abrir,
  crie um **atalho** para o `2-iniciar.bat` (botão direito no `.bat` → Criar atalho → arraste o atalho
  para lá).
- **Tailscale ativo antes do login (opcional):** ícone do Tailscale → *Preferences* → **Run unattended**.

## 8. Backup
Dê dois cliques em **`fazer-backup.bat`** sempre que quiser (pode ser com o sistema ligado). Ele cria
`backend\data\backups\backup_<data>.zip` com banco, imagens e recortes, e mantém os 14 mais recentes.

**Cópia automática para a nuvem:** se você usa o Google Drive para computador, coloque no `.env`, por
exemplo:
```
BACKUP_COPY_DIR=G:\Meu Drive\Backups Provas
```
Para rodar todo dia sozinho, use o Agendador de Tarefas do Windows: *Criar Tarefa Básica* → Diariamente
→ *Iniciar um programa* → escolha o `fazer-backup.bat`.

Restaurar um backup: rode o `3-parar.bat` e, no PowerShell, dentro da pasta `backend`:
```powershell
$env:DATA_DIR = "$PWD\data"
python -m app.backup --restore data\backups\backup_AAAA-MM-DD_HHMMSS.zip
```
Depois rode o `2-iniciar.bat`.

## 9. Atualizar o sistema (quando eu mandar uma versão nova)
1. `3-parar.bat`.
2. Extraia o zip novo **por cima** da pasta atual. O `servidor-pc\.env` e o `backend\data` não vêm no zip,
   então são preservados.
3. `1-instalar.bat` (ele mantém os segredos que já existem) e depois `2-iniciar.bat`.

---

## Problemas comuns
| Sintoma | O que fazer |
|---|---|
| "Não encontrei 'python'" | Instale pelo python.org marcando "Add python.exe to PATH" (a versão da Microsoft Store pode dar problema) |
| "A API não subiu" | Veja `servidor-pc\logs\api-erros.log`. Se falar de "insegura", o `.env` foi alterado: confira `QR_SECRET` e `AUTH_SECRET` |
| "já está rodando" ao iniciar | Já estava no ar; para reiniciar, use `3-parar.bat` e depois `2-iniciar.bat` |
| Endereço público não abre | O PC está ligado? O Tailscale está conectado (ícone)? Rode `4-publicar.bat` de novo |
| App diz "Sem conexão" | Confira o endereço no app (sem `https://`) e abra o mesmo endereço no navegador do celular |
| "Muitas tentativas" no login | 10 senhas erradas em 15 min para aquele e-mail; espere ou reinicie (3-parar, 2-iniciar) |

**Limites do plano grátis do Tailscale:** é para uso pessoal, não comercial. Se um dia você vender o
sistema para escolas, passe para um plano pago ou um servidor.
