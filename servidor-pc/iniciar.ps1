# 2-iniciar: sobe a API (só para este PC) e o painel (que o Tailscale publica na internet).
. (Join-Path $PSScriptRoot "comum.ps1")
Carregar-Env
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

if ((Porta-Ocupada 8000) -or (Porta-Ocupada 3000)) {
    Write-Host "Parece que o sistema já está rodando (portas 8000/3000 em uso). Use o 3-parar.bat antes, se quiser reiniciar." -ForegroundColor Yellow
    Start-Sleep -Seconds 6
    exit 0
}

Start-Process -FilePath "python" -WorkingDirectory $Backend -WindowStyle Hidden `
    -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1",
                    "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1") `
    -RedirectStandardOutput (Join-Path $Logs "api.log") -RedirectStandardError (Join-Path $Logs "api-erros.log")

if (-not (Esperar-Saude "http://127.0.0.1:8000/health" 40)) {
    Escrever-Erro "A API não subiu. Veja $Logs\api-erros.log"
    Get-Content (Join-Path $Logs "api-erros.log") -Tail 15 -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 20
    exit 1
}

Start-Process -FilePath "npm.cmd" -WorkingDirectory $Web -WindowStyle Hidden `
    -ArgumentList @("run", "start", "--", "-H", "127.0.0.1") `
    -RedirectStandardOutput (Join-Path $Logs "painel.log") -RedirectStandardError (Join-Path $Logs "painel-erros.log")

if (-not (Esperar-Saude "http://127.0.0.1:3000/health" 60)) {
    Escrever-Erro "O painel não subiu. Veja $Logs\painel-erros.log (rodou o 1-instalar.bat?)"
    Start-Sleep -Seconds 20
    exit 1
}

Escrever-Ok "Sistema no ar."
Write-Host "  Neste PC:   http://127.0.0.1:3000"
$pub = Endereco-Publico
if ($pub) { Write-Host "  Internet:   $pub   (painel e app)" -ForegroundColor Green }
else { Write-Host "  Internet:   Tailscale não encontrado. Veja o passo 'Publicar' no LEIA-ME." -ForegroundColor Yellow }
Start-Sleep -Seconds 10
