@echo off
rem Confere se esta tudo certo. De duplo clique neste arquivo.
cd /d "%~dp0"
title Verificacao do LocalAgent

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente ainda nao foi criado. De duplo clique em instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

echo.
echo [1/2] Testes automaticos do projeto...
.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

echo.
echo [2/2] Conexao com a IA (Ollama)...
.venv\Scripts\python.exe scripts\check_ollama.py

echo.
echo Fim. Aperte qualquer tecla para fechar.
pause >nul
