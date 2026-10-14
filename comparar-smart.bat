@echo off
rem Rodada curta: so os candidatos a SMART (4 perfis, de 1,5 a 2,5 horas). Nao pergunta nada; os modelos ja estao baixados.
rem Se parar no meio, de duplo clique de novo: ele continua de onde parou.
call "%~dp0comparar.bat" --perfis smart --sim %*
