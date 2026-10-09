# Instalador do LocalAgent para Windows 10/11.
# Uso normal: de um duplo clique em instalar.bat (ele chama este script).
# Simulacao (nao instala nada):  instalar.bat -DryRun
param(
    [switch]$DryRun,
    [switch]$SkipModel,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$LogFile = Join-Path $LogDir "instalacao.log"
try { Start-Transcript -Path $LogFile -Append | Out-Null } catch { }

$TotalSteps = 7
$Warnings = New-Object System.Collections.Generic.List[string]

function Say([string]$Message, [string]$Color = "White") {
    Write-Host $Message -ForegroundColor $Color
}

function Step([int]$Number, [string]$Message) {
    Say ""
    Say "[$Number/$TotalSteps] $Message" "Cyan"
}

function Warn([string]$Message) {
    $Warnings.Add($Message)
    Say "  AVISO: $Message" "Yellow"
}

function Have([string]$Command) {
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    # Depois de instalar programas, o PATH desta janela fica desatualizado.
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Ask-YesNo([string]$Question) {
    if ($DryRun) { return $true }
    $answer = Read-Host "$Question (S/N)"
    return @("S", "SIM", "Y", "YES") -contains $answer.Trim().ToUpper()
}

function Winget-Install([string]$Id, [string]$Label) {
    if ($DryRun) {
        Say "  (simulacao) winget install $Id" "Yellow"
        return
    }

    if (-not (Have "winget")) {
        throw "O winget nao foi encontrado. Abra a Microsoft Store, atualize o 'Instalador de Aplicativo' e rode instalar.bat de novo."
    }

    Say "  Instalando $Label (pode demorar alguns minutos)..."
    winget install --id $Id -e --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

function Get-PythonCommand {
    # Retorna "python" ou "py" se existir um Python 3.10+ funcionando (ignora o atalho da Store).
    foreach ($name in @("python", "py")) {
        if (-not (Have $name)) { continue }

        try {
            if ($name -eq "py") {
                $version = & py -3 -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            } else {
                $version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            }

            $parts = ("$version").Trim().Split(".")

            if ($parts.Count -ge 2 -and [int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                return $name
            }
        } catch { }
    }

    return $null
}

function Invoke-Python([string]$PythonCommand, [string[]]$Arguments) {
    if ($PythonCommand -eq "py") {
        & py -3 @Arguments
    } else {
        & python @Arguments
    }
}

Say "=============================================" "Green"
Say "  Instalador do LocalAgent (Windows)"          "Green"
Say "=============================================" "Green"
Say "Pasta do projeto: $Root"
if ($DryRun) { Say "MODO SIMULACAO: nada sera instalado ou alterado." "Yellow" }

try {

    # ---------------------------------------------------------------- 1. Python
    Step 1 "Verificando o Python 3.10 ou mais novo"
    $python = Get-PythonCommand

    if ($python) {
        Say "  Python encontrado." "Green"
    } else {
        Say "  Python nao encontrado. Vou instalar o Python 3.12."
        Winget-Install "Python.Python.3.12" "Python 3.12"
        $python = Get-PythonCommand

        if (-not $python -and -not $DryRun) {
            throw "O Python foi instalado, mas esta janela ainda nao o enxerga. Feche esta janela e de duplo clique em instalar.bat de novo."
        }
    }

    # ---------------------------------------------------------------- 2. Git
    Step 2 "Verificando o Git"
    if (Have "git") {
        Say "  Git encontrado." "Green"
    } else {
        Winget-Install "Git.Git" "Git"
    }

    # ---------------------------------------------------------------- 3. Ollama
    Step 3 "Verificando o Ollama (programa que roda a IA)"
    if (Have "ollama") {
        Say "  Ollama encontrado." "Green"
    } else {
        Winget-Install "Ollama.Ollama" "Ollama"

        if (-not (Have "ollama") -and -not $DryRun) {
            throw "O Ollama foi instalado, mas esta janela ainda nao o enxerga. Feche esta janela e de duplo clique em instalar.bat de novo."
        }
    }

    # ---------------------------------------------------------------- 4. Placa de video
    Step 4 "Verificando a placa de video NVIDIA"
    if (Have "nvidia-smi") {
        try {
            $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null) -join "; "
            Say "  Encontrada: $gpu" "Green"
        } catch {
            Warn "nvidia-smi existe mas falhou. Atualize o driver da NVIDIA."
        }
    } else {
        Warn "Driver da NVIDIA nao encontrado. Sem ele a IA roda no processador e fica MUITO lenta. Baixe o driver em nvidia.com/drivers (ou pelo GeForce Experience) e rode instalar.bat de novo."
    }

    # ---------------------------------------------------------------- 5. Ambiente do projeto
    Step 5 "Criando o ambiente do projeto (pasta .venv) e instalando as bibliotecas"
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"

    if ($DryRun) {
        Say "  (simulacao) python -m venv .venv" "Yellow"
        Say "  (simulacao) pip install -r requirements-dev.txt" "Yellow"
    } else {
        $venvOk = $false

        if (Test-Path $venvPython) {
            # Um .venv copiado de outro computador existe, mas nao funciona aqui.
            try {
                & $venvPython -c "import sys" *> $null
                $venvOk = ($LASTEXITCODE -eq 0)
            } catch { $venvOk = $false }
        }

        if ($venvOk) {
            Say "  Ambiente .venv ja existe e funciona, reaproveitando." "Green"
        } else {
            if (Test-Path (Join-Path $Root ".venv")) {
                Say "  O .venv existente nao funciona neste computador. Recriando..." "Yellow"
                Remove-Item -Recurse -Force (Join-Path $Root ".venv")
            }

            Invoke-Python $python @("-m", "venv", ".venv")
        }

        & $venvPython -m pip install --disable-pip-version-check --upgrade pip
        & $venvPython -m pip install --disable-pip-version-check -r requirements-dev.txt
        Say "  Bibliotecas instaladas." "Green"
    }

    # ---------------------------------------------------------------- 6. Testes
    Step 6 "Rodando os testes automaticos do projeto"
    if ($SkipTests) {
        Say "  Pulado (-SkipTests)." "Yellow"
    } elseif ($DryRun) {
        Say "  (simulacao) python -m pytest tests -q" "Yellow"
    } else {
        & $venvPython -m pytest tests -q -p no:cacheprovider
        if ($LASTEXITCODE -eq 0) {
            Say "  Todos os testes passaram." "Green"
        } else {
            Warn "Alguns testes falharam. O agente pode funcionar, mas envie a pasta 'logs' (tem o instalacao.log) para quem estiver te ajudando."
        }
    }

    # ---------------------------------------------------------------- 7. Modelo de IA
    Step 7 "Baixando o modelo de IA principal"
    $model = "qwen3:8b"
    $registry = Join-Path $Root "models\registry.json"

    if (Test-Path $registry) {
        try {
            $configured = (Get-Content $registry -Raw -Encoding UTF8 | ConvertFrom-Json).active_fast_model
            if ($configured) { $model = $configured }
        } catch { }
    }

    if ($SkipModel) {
        Say "  Pulado (-SkipModel)." "Yellow"
    } elseif ($DryRun) {
        Say "  (simulacao) ollama pull $model" "Yellow"
    } else {
        & ollama list *> $null
        if ($LASTEXITCODE -ne 0) {
            Say "  Iniciando o servico do Ollama..."
            Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden

            for ($i = 0; $i -lt 30; $i++) {
                Start-Sleep -Seconds 1
                & ollama list *> $null
                if ($LASTEXITCODE -eq 0) { break }
            }
        }

        $installed = (& ollama list 2>$null) -join "`n"

        if ($installed -match [regex]::Escape($model)) {
            Say "  O modelo $model ja esta baixado." "Green"
        } elseif (Ask-YesNo "  Baixar o modelo $model agora? (cerca de 5 GB, precisa de internet)") {
            & ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Warn "O download do modelo falhou. Rode de novo mais tarde com:  ollama pull $model"
            } else {
                Say "  Modelo baixado." "Green"
            }
        } else {
            Warn "Modelo nao baixado. Antes de usar o agente, rode:  ollama pull $model"
        }
    }

    # ---------------------------------------------------------------- fim
    Say ""
    Say "=============================================" "Green"
    if ($Warnings.Count -eq 0) {
        Say "  PRONTO! Instalacao concluida." "Green"
    } else {
        Say "  Instalacao concluida COM AVISOS:" "Yellow"
        foreach ($w in $Warnings) { Say "   - $w" "Yellow" }
    }
    Say "=============================================" "Green"
    Say ""
    Say "Para usar:      de duplo clique em  iniciar.bat"
    Say "Para conferir:  de duplo clique em  verificar.bat"
    Say "Manual:         abra o arquivo  LEIA-ME-WINDOWS.md"

} catch {
    Say ""
    Say "ERRO: $($_.Exception.Message)" "Red"
    Say "A instalacao parou. O texto acima ficou salvo em logs\instalacao.log." "Red"
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}

try { Stop-Transcript | Out-Null } catch { }
exit 0
