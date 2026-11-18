# 1-instalar: dependências, segredos e build do painel. Pode rodar de novo quando atualizar o sistema.
. (Join-Path $PSScriptRoot "comum.ps1")

Exigir-Comando python "Instale o Python 3.11+ (python.org) marcando 'Add python.exe to PATH'."
Exigir-Comando npm "Instale o Node.js 20+ (nodejs.org)."

if (Criar-EnvSeNaoExiste) { Escrever-Ok "Criei $EnvFile com segredos novos. Guarde uma cópia dele!" }
else { Write-Host "Usando o $EnvFile que já existe (segredos mantidos)." }

Push-Location $Backend
Rodar "Instalando a API (Python)" { python -m pip install -r requirements.txt }
Rodar "Instalando o Chromium (gera os PDFs)" { python -m playwright install chromium }
Pop-Location

Push-Location $Web
Rodar "Instalando o painel (Node.js)" { npm ci --no-audit --no-fund }
# "/" = o painel fala com a API pelo próprio endereço (ele repassa /v1 para a API).
$env:NEXT_PUBLIC_API_URL = "/"
Rodar "Montando o painel (pode levar 1-2 minutos)" { npm run build }
Pop-Location

Escrever-Ok "`nInstalação concluída. Agora rode o 2-iniciar.bat."
