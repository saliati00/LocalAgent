@echo off
rem Instalador do LocalAgent. De duplo clique neste arquivo.
cd /d "%~dp0"
title Instalador do LocalAgent
echo.
echo ================================================
echo   Instalador do LocalAgent
echo   Pode demorar. Nao feche esta janela.
echo ================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1" %*
echo.
echo ------------------------------------------------
echo Fim. Aperte qualquer tecla para fechar.
pause >nul
