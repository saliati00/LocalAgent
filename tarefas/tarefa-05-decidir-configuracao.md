# Tarefa 05 — Decidir a configuração de modelos (roteiro do usuário)

Quem faz: **usuário**
Pré-requisitos: tarefas 03 e 04 concluídas
Tamanho: algumas horas (a maior parte é esperar o modelo rodar)

## Objetivo
Comparar as configurações com os mesmos dados e escolher uma, em vez de decidir no escuro.

## Configurações a comparar
- A: só o FAST (qwen3:8b) como está.
- B: só o FAST com raciocínio ligado (`think=True`).
- C: só o SMART (14B ou outro candidato).
- D: FAST com escalada para o SMART.

## Passos (você faz, com ajuda de quem estiver te orientando)
1. Para cada configuração, rode as tarefas de `scripts/eval/tarefas/` pelo menos 3 vezes cada e registre acertos e tempo.
2. Calcule a taxa de sucesso e o tempo médio por tarefa (use `summarize` do `runner.py`).
3. Anote também quantas vezes terminou em `needs_human` e quantos tokens/s apareceu no `ollama ps`.
4. Registre a tabela em `specs/avaliacoes.md`.
5. Regra de decisão sugerida: só adote o SMART se ele ganhar do FAST com folga (por exemplo, +20 pontos de acerto) e o tempo for aceitável para você.

## Pronto quando
Existe `specs/avaliacoes.md` com a tabela e uma linha dizendo qual configuração foi escolhida e por quê.

## Observação
Não baixe o 14B antes das tarefas 03 e 04. Este item aparece como `[humano]` na FASE 11 da especificação.
