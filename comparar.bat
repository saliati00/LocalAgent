@echo off
rem Compara modelos (qwen3:8b x qwen3.5:9b x qwen3.5:4b) com a mesma bateria. De duplo clique.
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LocalAgent - comparar modelos

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente ainda nao foi criado. De duplo clique em instalar.bat primeiro.
    pause
    exit /b 1
)

ollama list >nul 2>&1
if errorlevel 1 (
    echo Iniciando o Ollama...
    start "" /min ollama serve
    timeout /t 8 /nobreak >nul
)

echo Isto pode levar varias horas (uma bateria completa por modelo). Deixe rodando a noite.
echo Se voce ja rodou a bateria com o qwen3:8b, use:  comparar.bat --base logs\bateria\NOME_DA_PASTA
echo.
.venv\Scripts\python.exe scripts\comparar_modelos.py %*

echo.
echo Pronto. Leve a pasta logs\comparacao e o arquivo logs\agent.log. Aperte qualquer tecla.
pause >nul
