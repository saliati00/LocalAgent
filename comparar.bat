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

echo Se uma rodada anterior nao terminou (travou, queda de luz), este programa CONTINUA dela sozinho.
echo Para comecar do zero:  comparar.bat --nova
echo.
echo Isto leva cerca de 3 a 4 horas (FAST: 9b-kv8, 9b-16k-kv8; depois SMART: gemma4:12b, gpt-oss:20b, par 9b+gemma, par 9b+gpt-oss). Deixe rodando e nao mexa no computador.
echo So o FAST:  comparar.bat --perfis fast      So o SMART:  comparar.bat --perfis smart
echo.
.venv\Scripts\python.exe scripts\comparar_modelos.py %*

echo.
echo Pronto. Compacte a pasta logs inteira e envie. Nao precisa anotar nem copiar nada. Aperte qualquer tecla.
pause >nul
