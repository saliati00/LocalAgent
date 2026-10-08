@echo off
rem Roda a bateria automatica em cada modelo (qwen3:8b, qwen3.5:9b, qwen3.5:4b) e compara. De duplo clique.
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

echo Isto leva cerca de 30 a 40 minutos (uma bateria por modelo). Deixe rodando e nao mexa no computador.
echo Versao curta:  comparar.bat --rapido
echo.
.venv\Scripts\python.exe scripts\comparar_modelos.py %*

echo.
echo Pronto. Leve a pasta logs\comparacao e o arquivo logs\agent.log. Aperte qualquer tecla.
pause >nul
