# Funções compartilhadas pelos scripts do servidor no PC (Windows PowerShell 5.1+).
$Raiz    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Raiz "backend"
$Web     = Join-Path $Raiz "web"
$EnvFile = Join-Path $PSScriptRoot ".env"
$Logs    = Join-Path $PSScriptRoot "logs"

function Escrever-Erro($msg) { Write-Host $msg -ForegroundColor Red }
function Escrever-Ok($msg)   { Write-Host $msg -ForegroundColor Green }

function Exigir-Comando($cmd, $dica) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Escrever-Erro "Não encontrei '$cmd'. $dica"
        exit 1
    }
}

# Roda um programa externo e para tudo se ele falhar.
function Rodar([string]$descricao, [scriptblock]$bloco) {
    Write-Host "`n>> $descricao" -ForegroundColor Cyan
    & $bloco
    if ($LASTEXITCODE -ne 0) {
        Escrever-Erro "Falhou: $descricao (código $LASTEXITCODE). Veja a mensagem acima."
        exit 1
    }
}

function Novo-Segredo { python -c "import secrets; print(secrets.token_hex(32))" }

function Criar-EnvSeNaoExiste {
    if (Test-Path $EnvFile) { return $false }
    $qr = Novo-Segredo
    $auth = Novo-Segredo
    $linhas = @(
        "# Configuração do servidor no PC. NÃO compartilhe este arquivo e guarde uma cópia em lugar seguro.",
        "# NUNCA troque o QR_SECRET depois de imprimir provas: os cartões impressos deixam de ser aceitos.",
        "QR_SECRET=$qr",
        "AUTH_SECRET=$auth",
        "",
        "# Mude para false depois de criar sua conta (e rode 3-parar e 2-iniciar).",
        "ALLOW_REGISTRATION=true",
        "",
        "# Quantos backups manter em backend\data\backups",
        "BACKUP_KEEP=14",
        "",
        "# Pasta extra para onde copiar cada backup (ex.: sua pasta do Google Drive). Vazio = não copia.",
        "BACKUP_COPY_DIR="
    )
    [System.IO.File]::WriteAllLines($EnvFile, $linhas, (New-Object System.Text.UTF8Encoding($false)))
    return $true
}

# Lê o .env e coloca as variáveis no ambiente deste processo (os programas iniciados herdam).
function Carregar-Env {
    if (-not (Test-Path $EnvFile)) {
        Escrever-Erro "Arquivo $EnvFile não existe. Rode primeiro o 1-instalar.bat."
        exit 1
    }
    foreach ($linha in Get-Content -Path $EnvFile -Encoding UTF8) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $valor = $Matches[2]
            if ($valor.Length -ge 2 -and $valor.StartsWith('"') -and $valor.EndsWith('"')) { $valor = $valor.Substring(1, $valor.Length - 2) }
            [Environment]::SetEnvironmentVariable($Matches[1], $valor, "Process")
        }
    }
    $env:APP_ENV = "production"
    $env:DATA_DIR = Join-Path $Backend "data"
}

function Porta-Ocupada([int]$porta) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $r = $c.BeginConnect("127.0.0.1", $porta, $null, $null)
        $ok = $r.AsyncWaitHandle.WaitOne(300) -and $c.Connected
        return [bool]$ok
    } catch { return $false } finally { $c.Close() }
}

function Esperar-Saude([string]$url, [int]$segundos) {
    for ($i = 0; $i -lt $segundos; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Achar-Tailscale {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $padrao = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if ($env:ProgramFiles -and (Test-Path $padrao)) { return $padrao }
    return $null
}

function Endereco-Publico {
    $ts = Achar-Tailscale
    if (-not $ts) { return $null }
    try {
        $st = (& $ts status --json) -join "`n" | ConvertFrom-Json
        $dns = $st.Self.DNSName
        if ($dns) { return "https://" + $dns.TrimEnd('.') }
    } catch { }
    return $null
}
