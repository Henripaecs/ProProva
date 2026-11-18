# Colocar o sistema num servidor (grátis, Oracle Cloud)

No fim você terá:
- o **painel** em `https://SEU-ENDERECO` (abre de qualquer computador ou celular);
- a **API** no mesmo endereço, que o **app** usa de qualquer lugar (não precisa mais estar no mesmo Wi-Fi);
- **HTTPS automático**, cadastro fechado depois da sua conta, limite de tentativas de senha e backup diário.

**Custo:** R$ 0 dentro do plano *Always Free* da Oracle (hoje: até 2 núcleos ARM e 12 GB de memória,
mais que suficiente). A Oracle pede um cartão no cadastro só para verificar a identidade.

---

## 1. Criar a conta na Oracle Cloud
1. Acesse **oracle.com/cloud/free** e crie a conta.
2. **Região inicial (home region):** escolha **Brazil East (São Paulo)**. Ela **não pode ser trocada depois**,
   e o plano grátis só vale nela.
3. Confirme o cartão (verificação; nada é cobrado no plano grátis).

## 2. Criar o servidor (VM)
Menu ☰ → **Compute → Instances → Create instance**.
- **Image:** Canonical **Ubuntu 24.04**.
- **Shape:** *Change shape* → **Ampere** → `VM.Standard.A1.Flex` → **2 OCPUs** e **12 GB**
  (não passe disso, senão sai do grátis).
- **Networking:** deixe criar a rede padrão e marque **Assign a public IPv4 address**.
- **SSH keys:** *Generate a key pair for me* → **Save private key** (guarde o arquivo `.key`).
- **Create.** Anote o **Public IP** que aparece (ex.: `129.146.10.20`).

> Se aparecer **"Out of capacity"**: tente outro *Availability domain* na mesma tela ou tente de novo mais
> tarde (é comum; a Oracle libera capacidade ao longo do dia).

## 3. Liberar as portas 80 e 443
**a) Na Oracle (firewall da rede):** na página da instância → *Subnet* → *Security Lists* →
*Default Security List* → **Add Ingress Rules**:
- Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination port **80**
- Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination port **443**

**b) No próprio Ubuntu da Oracle** (ele vem com firewall interno fechado). Conecte primeiro (passo 4) e rode:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 4. Conectar no servidor
No PowerShell do seu computador (troque o caminho da chave e o IP):
```powershell
ssh -i C:\Users\SEU_USUARIO\Downloads\ssh-key.key ubuntu@129.146.10.20
```
Se o Windows reclamar das permissões da chave: clique com o botão direito no arquivo → Propriedades →
Segurança → Avançadas → desabilite a herança e deixe só o seu usuário.

## 5. Instalar o Docker (no servidor)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```
Conecte de novo (passo 4) para valer a permissão.

## 6. Enviar o projeto
No PowerShell **do seu computador**:
```powershell
scp -i C:\Users\SEU_USUARIO\Downloads\ssh-key.key C:\caminho\omr-exam-system.zip ubuntu@129.146.10.20:~
```
No servidor:
```bash
sudo apt-get install -y unzip
unzip -o omr-exam-system.zip
cd omr-exam-system/deploy
```

## 7. Configurar
```bash
cp .env.example .env
mkdir -p data                 # pasta do banco (precisa ser criada por você, não pelo Docker)
openssl rand -hex 32          # rode duas vezes: um valor para QR_SECRET, outro para AUTH_SECRET
nano .env
```
No `.env`:
- `DOMAIN` → o IP **com traços** + `.sslip.io`. Ex.: IP `129.146.10.20` → `129-146-10-20.sslip.io`.
  (O sslip.io é um serviço gratuito que transforma o IP num nome, o que permite ter HTTPS sem comprar domínio.
  Se um dia comprar um domínio, é só trocar aqui.)
- `QR_SECRET` e `AUTH_SECRET` → os dois valores gerados.

Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.

> ⚠️ **Nunca troque o `QR_SECRET` depois de imprimir provas**: os QR Codes já impressos deixariam de ser aceitos.
> Guarde uma cópia do `.env` em lugar seguro (gerenciador de senhas).

## 8. Subir
```bash
docker compose up -d --build
```
A primeira vez demora alguns minutos (baixa e monta tudo). Depois:
```bash
docker compose ps            # os 3 serviços devem aparecer "running" (a api fica "healthy")
docker compose logs -f api   # Ctrl+C para sair
```
Abra **https://129-146-10-20.sslip.io** (o seu) no navegador. O cadeado do HTTPS pode levar 1 minuto
na primeira vez.

## 9. Criar sua conta e fechar o cadastro
1. No painel, **Criar conta**.
2. No servidor, mude `ALLOW_REGISTRATION=false` no `.env` (`nano .env`) e aplique:
   ```bash
   docker compose up -d
   ```
   Agora ninguém mais consegue criar conta no seu servidor. (Para cadastrar outro professor, volte para
   `true`, crie, e feche de novo.)

## 10. App
No app, em **Servidor**, digite só `129-146-10-20.sslip.io` (o app usa HTTPS automaticamente para
endereços assim). Funciona no 4G, em qualquer lugar.

## 11. Backup automático
No servidor:
```bash
chmod +x ~/omr-exam-system/deploy/backup.sh
~/omr-exam-system/deploy/backup.sh       # teste: cria deploy/data/backups/backup_....zip
crontab -e                               # escolha o nano e adicione a linha abaixo no fim:
0 3 * * * /home/ubuntu/omr-exam-system/deploy/backup.sh >> /home/ubuntu/backup.log 2>&1
```
Todo dia às 3h sai um backup; ficam os 14 mais recentes. **Copie de vez em quando para fora do servidor**
(se a conta Oracle tiver problema, o servidor vai junto). No seu computador:
```powershell
scp -i C:\...\ssh-key.key "ubuntu@129.146.10.20:~/omr-exam-system/deploy/data/backups/*" C:\Backups\provas\
```
Restaurar (no servidor):
```bash
cd ~/omr-exam-system/deploy
docker compose stop api
docker compose run --rm api python -m app.backup --restore /data/backups/backup_AAAA-MM-DD_HHMMSS.zip
docker compose start api
```

## 12. Atualizar o sistema (quando eu te mandar uma versão nova)
Envie o zip novo (passo 6) e no servidor:
```bash
cd ~ && unzip -o omr-exam-system.zip
cd omr-exam-system/deploy && docker compose up -d --build
```
O `.env` e a pasta `data/` não vêm no zip, então são preservados.

---

## Cuidados
- **Instância ociosa:** a Oracle pode recuperar instâncias do plano grátis que ficam paradas por dias
  (quase sem uso de processador, rede e memória). Use o sistema regularmente e mantenha o backup em dia.
  Se quiser eliminar esse risco, dá para converter a conta para *Pay As You Go*: continua gratuito dentro
  dos limites do *Always Free*, mas aí vale criar um alerta de orçamento (Billing → Budgets) de R$ 1 para
  ser avisado se algo sair do grátis.
- **Dados de alunos (LGPD):** só você deve ter a senha do painel e a chave SSH. Excluir um aluno no painel
  apaga as correções dele. Os backups contêm nomes e notas: guarde-os com o mesmo cuidado.
- **Dados que você já tem no computador:** recomendo começar do zero no servidor, porque os cartões
  impressos no computador foram gerados com outro `QR_SECRET` e não seriam aceitos lá.

## Problemas comuns
| Sintoma | Causa provável |
|---|---|
| Navegador não abre o endereço | Portas 80/443 fechadas: confira os passos 3a **e** 3b |
| "Não seguro" / erro de certificado | Espere 1–2 min; confira se `DOMAIN` bate com o IP; veja `docker compose logs caddy` |
| `api` reiniciando sem parar | `docker compose logs api` — quase sempre segredo vazio/curto no `.env` |
| Erro de permissão em `/data` | Você esqueceu o `mkdir -p data` antes de subir: `sudo chown -R 1000:1000 data` |
| "Muitas tentativas" no login | 10 senhas erradas em 15 min para o mesmo e-mail; espere ou reinicie a api |
| PDF da turma não sai | `docker compose logs api`; o servidor precisa de pelo menos ~1 GB de memória livre |
