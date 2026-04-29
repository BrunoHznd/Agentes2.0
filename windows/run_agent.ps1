# Configurações do agente (edite conforme o PC/localidade)
$env:AGENT_SITE = if ($env:AGENT_SITE) { $env:AGENT_SITE } else { "galpao" }
$env:AGENT_NAME = if ($env:AGENT_NAME) { $env:AGENT_NAME } else { "agente-$(Get-Random -Minimum 1000 -Maximum 9999)" }
$env:AGENT_SERVER = if ($env:AGENT_SERVER) { $env:AGENT_SERVER } else { "http://localhost:9000" }

# Preencha o token se o servidor exigir (em dev, pode ficar vazio)
$env:AGENT_TOKEN = if ($env:AGENT_TOKEN) { $env:AGENT_TOKEN } else { "" }

# Intervalo em segundos entre as execuções (apenas quando AGENT_LOOP=1)
$env:AGENT_INTERVAL_SEC = if ($env:AGENT_INTERVAL_SEC) { $env:AGENT_INTERVAL_SEC } else { "60" }

# 1 para rodar continuamente, 0 para executar uma vez
$env:AGENT_LOOP = if ($env:AGENT_LOOP) { $env:AGENT_LOOP } else { "1" }

# Intervalo para verificar comandos do servidor (segundos)
$env:AGENT_COMMAND_CHECK_INTERVAL = if ($env:AGENT_COMMAND_CHECK_INTERVAL) { $env:AGENT_COMMAND_CHECK_INTERVAL } else { "5" }

# Ativar/desativar teste de velocidade (1 ou 0)
$env:AGENT_SPEEDTEST = if ($env:AGENT_SPEEDTEST) { $env:AGENT_SPEEDTEST } else { "1" }

# Tamanho dos dados para teste de velocidade (em bytes)
$env:AGENT_SPEEDTEST_DOWNLOAD_BYTES = if ($env:AGENT_SPEEDTEST_DOWNLOAD_BYTES) { $env:AGENT_SPEEDTEST_DOWNLOAD_BYTES } else { "1048576" } # 1MB
$env:AGENT_SPEEDTEST_UPLOAD_BYTES = if ($env:AGENT_SPEEDTEST_UPLOAD_BYTES) { $env:AGENT_SPEEDTEST_UPLOAD_BYTES } else { "524288" } # 0.5MB

# Exibir configurações
Write-Host "=== Configuração do Agente ===" -ForegroundColor Cyan
Write-Host "Site: $env:AGENT_SITE"
Write-Host "Nome do Agente: $env:AGENT_NAME"
Write-Host "Servidor: $env:AGENT_SERVER"
Write-Host "Modo Loop: $($env:AGENT_LOOP)"
Write-Host "Intervalo (s): $env:AGENT_INTERVAL_SEC"
Write-Host "Verificação de Comandos (s): $env:AGENT_COMMAND_CHECK_INTERVAL"
Write-Host "Teste de Velocidade: $($env:AGENT_SPEEDTEST)"
Write-Host "=============================" -ForegroundColor Cyan

# Verificar se o Python está instalado
$pythonCommand = "python"
$pythonVersion = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python não encontrado no PATH. Verifique se o Python está instalado." -ForegroundColor Red
    exit 1
}

# Tentar encontrar o ambiente virtual
$agentDir = $PSScriptRoot
$venvPython = Join-Path $agentDir ".venv/Scripts/python.exe"

# Verificar se o ambiente virtual existe
if (Test-Path $venvPython) {
    Write-Host "Usando ambiente virtual em: $venvPython" -ForegroundColor Green
    $pythonCommand = $venvPython
} else {
    Write-Host "Usando Python do sistema: $(python --version)" -ForegroundColor Yellow
}

# Instalar dependências se necessário
$requirementsFile = Join-Path $agentDir "requirements.txt"
if (Test-Path $requirementsFile) {
    Write-Host "Verificando dependências..." -ForegroundColor Cyan
    if ($pythonCommand -eq "python") {
        & pip install -r $requirementsFile
    } else {
        & $pythonCommand -m pip install -r $requirementsFile
    }
}

# Iniciar o agente
Write-Host "\nIniciando agente..." -ForegroundColor Green
& $pythonCommand (Join-Path $agentDir "agent.py")
