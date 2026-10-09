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
echo Isto leva de 12 a 18 horas (FAST: 9b, 4b, 9b-kv8, 4b-16k-kv8, 8b; depois SMART: gemma4:12b, gpt-oss:20b, par 9b+gemma, qwen3-coder:30b). Deixe rodando e nao mexa no computador.
echo Separar em duas noites:  comparar.bat --perfis fast   e depois   comparar.bat --perfis smart
echo Versao curta (2 a 3 horas):  comparar.bat --perfis 9b,4b
echo.
.venv\Scripts\python.exe scripts\comparar_modelos.py %*

echo.
echo Pronto. Leve a pasta logs\comparacao e o arquivo logs\agent.log. Aperte qualquer tecla.
pause >nul
