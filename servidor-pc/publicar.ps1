# 4-publicar: liga o Tailscale Funnel (endereço https público apontando para o painel). Rode UMA vez.
. (Join-Path $PSScriptRoot "comum.ps1")
$ts = Achar-Tailscale
if (-not $ts) {
    Escrever-Erro "Tailscale não encontrado. Instale em tailscale.com/download, entre na sua conta e rode de novo."
    Start-Sleep -Seconds 15
    exit 1
}
Write-Host "Ligando o Funnel... Se aparecer um link, abra no navegador, autorize e rode este script de novo."
& $ts funnel --bg 3000
if ($LASTEXITCODE -eq 0) {
    $pub = Endereco-Publico
    Escrever-Ok "`nPublicado! Endereço: $pub"
    Write-Host "Use este endereço no navegador e, no app, digite só a parte depois de https://"
}
Start-Sleep -Seconds 20
