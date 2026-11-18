# backup: banco + imagens + recortes num .zip (pode rodar com o sistema ligado).
. (Join-Path $PSScriptRoot "comum.ps1")
Carregar-Env
Push-Location $Backend
$saida = python -m app.backup
$codigo = $LASTEXITCODE
Pop-Location
if ($codigo -ne 0) { Escrever-Erro "Backup falhou."; exit 1 }
Write-Host $saida
$pasta = Join-Path $Backend "data\backups"
$ultimo = Get-ChildItem -Path $pasta -Filter "backup_*.zip" | Sort-Object Name | Select-Object -Last 1
if ($env:BACKUP_COPY_DIR -and $ultimo) {
    New-Item -ItemType Directory -Force -Path $env:BACKUP_COPY_DIR | Out-Null
    Copy-Item -Path $ultimo.FullName -Destination $env:BACKUP_COPY_DIR -Force
    Escrever-Ok "Cópia enviada para $env:BACKUP_COPY_DIR"
}
