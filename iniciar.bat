@echo off
rem Inicia o LocalAgent. De duplo clique neste arquivo.
cd /d "%~dp0"
title LocalAgent

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

.venv\Scripts\python.exe agent.py

echo.
echo O agente foi encerrado. Aperte qualquer tecla para fechar.
pause >nul
