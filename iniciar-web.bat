@echo off
rem Chat do LocalAgent no navegador (so FAST). De duplo clique.
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LocalAgent - Chat

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente ainda nao foi criado.
    echo De duplo clique em instalar.bat primeiro.
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
echo O chat foi encerrado. Aperte qualquer tecla para fechar.
pause >nul
