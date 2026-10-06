# Tarefa 04 — Medição no PC (roteiro do usuário)

Quem faz: **usuário** (o agente só ajuda nos passos simples)
Pré-requisitos: instalação concluída (`instalar.bat` e `verificar.bat`)
Tamanho: ~30 minutos

## Objetivo
Medir o consumo real de contexto e a velocidade do modelo neste PC. É o dado que decide o `NUM_CTX`, se há SMART e se vale subir a RAM.

## Passos (você faz)
1. Rode `ollama --version` e anote o número.
2. Abra `iniciar.bat` e peça, uma de cada vez, estas 6 tarefas:
   - `Verifique se git e python estão instalados.`
   - `Liste os arquivos da pasta workspace e me diga o que são.`
   - `Crie o arquivo workspace/ola.txt com o texto "oi".`
   - `dê continuidade à tarefa 1`
   - `Pesquise qual é o repositório oficial do llama.cpp e me diga a URL.`
   - `Leia o arquivo LEIA-ME-WINDOWS.md e resuma em 5 linhas.`
3. Com o agente respondendo, abra outro Prompt de Comando e rode `ollama ps`. Anote as colunas SIZE, PROCESSOR (quanto na GPU e quanto na CPU) e CONTEXT.
4. Feche o agente e rode `.venv\Scripts\python scripts\summarize_logs.py`. Ele resume o `logs\agent.log` (tamanho do prompt, tokens, avisos de contexto, escaladas).
5. Anote sua impressão: velocidade (rápido, ok, lento), quantas confirmações pediu, se travou.
6. Salve tudo em um arquivo `medicoes.md` e mostre a quem for ajudar a decidir.

## Pronto quando
Você tem: versão do Ollama, saída do `ollama ps`, saída do `summarize_logs.py` e sua impressão.

## Se travar
Se o agente não responder em 2 minutos na primeira tarefa, anote a mensagem de erro e rode `verificar.bat`.

## Observação
Este item aparece como `[humano]` na FASE 11 da especificação: só você o marca como concluído.
