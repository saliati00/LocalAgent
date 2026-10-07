@echo off
rem Roda a bateria automatica de testes (sem digitar nada). De duplo clique.
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LocalAgent - bateria de testes

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

echo Isto leva de 1 a 1,5 hora. Pode deixar rodando e nao mexa no computador.
echo Para a versao curta, feche e rode:  bateria.bat --rapido
echo.
.venv\Scripts\python.exe scripts\bateria.py %*

echo.
echo Pronto. Leve a pasta logs\bateria e o arquivo logs\agent.log. Aperte qualquer tecla.
pause >nul
