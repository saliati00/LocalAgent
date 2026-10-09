@echo off
rem Igual ao comparar.bat, mas baixa os modelos que faltarem SEM perguntar (S/N).
rem Use para deixar rodando sozinho do inicio ao fim. Se parar no meio, de duplo clique de novo: ele continua.
call "%~dp0comparar.bat" --sim %*
