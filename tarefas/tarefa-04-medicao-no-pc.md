# Tarefa 04 — Medição no PC (roteiro do usuário)

Quem faz: **usuário** (o agente só ajuda nos passos simples)
Pré-requisitos: instalação concluída (`instalar.bat` e `verificar.bat`)
Tamanho: ~30 minutos

## Objetivo
Medir o consumo real de contexto e a velocidade do modelo neste PC. É o dado que decide o `NUM_CTX`, se há SMART e se vale subir a RAM.

## Passos (você faz)
Siga o roteiro completo em **`ROTEIRO-DE-TESTES.md`** (na raiz do projeto): são 8 testes, na ordem, com o que esperar, o que anotar e uma tabela de resultados para preencher. Resumo:
1. Versão do Ollama e `verificar.bat`.
2. Três tarefas pequenas e a tarefa 1 (com o teste de aceite).
3. A tarefa 1 repetida, seguida de `scripts\summarize_logs.py` (detecta loops e contexto cheio).
4. `ollama ps` com o agente respondendo (GPU e CPU, contexto).
5. Testes de segurança (confirmação e arquivo protegido) e a tarefa 2.

## Pronto quando
Você tem: versão do Ollama, saída do `ollama ps`, saída do `summarize_logs.py` e sua impressão.

## Se travar
Se o agente não responder em 2 minutos na primeira tarefa, anote a mensagem de erro e rode `verificar.bat`.

## Observação
Este item aparece como `[humano]` na FASE 11 da especificação: só você o marca como concluído.
