# 3-parar: encerra a API e o painel.
. (Join-Path $PSScriptRoot "comum.ps1")
$parou = $false
foreach ($porta in 8000, 3000) {
    $conexoes = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conexoes) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        $parou = $true
    }
}
if ($parou) { Escrever-Ok "Sistema parado." } else { Write-Host "Nada rodando nas portas 8000/3000." }
Start-Sleep -Seconds 3
