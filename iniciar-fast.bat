@echo off
rem LocalAgent so com o modelo FAST: nunca chama o SMART. De duplo clique.
rem O comportamento padrao (iniciar.bat) nao muda; so este arquivo liga o modo.
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set LOCALAGENT_SO_FAST=1
title LocalAgent (so FAST)

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
