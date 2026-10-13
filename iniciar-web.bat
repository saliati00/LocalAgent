@echo off
rem Interface web do LocalAgent (Open WebUI + agente so FAST). De duplo clique.
rem Tudo roda e fica dentro desta pasta: .venv-webui (programa) e data-webui (conversas).
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LocalAgent - Interface web

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente ainda nao foi criado.
    echo De duplo clique em instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

if not exist ".venv-webui\Scripts\open-webui.exe" (
    echo A interface web nao esta instalada.
    echo De duplo clique em instalar.bat; se ele avisar que o Python 3.11 ou 3.12 nao foi encontrado, instale um deles e rode de novo.
    echo.
    pause
    exit /b 1
)

ollama list >nul 2>&1
if errorlevel 1 (
    echo Iniciando o Ollama...
    start "" /min ollama serve
    timeout /t 8 /nobreak >nul
)

.venv\Scripts\python.exe scripts\iniciar_web.py

echo.
echo A interface foi encerrada. Aperte qualquer tecla para fechar.
pause >nul
