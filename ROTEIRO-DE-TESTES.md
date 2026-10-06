# Roteiro de testes no PC (primeira rodada)

Para quem: **você**, depois de rodar o `instalar.bat`. Tempo: cerca de 1 hora (a maior parte é esperar o modelo responder).

## Regras desta rodada
- Faça **uma coisa por vez**, na ordem.
- **Não mude nenhuma configuração** entre os testes (assim os números ficam comparáveis).
- **Não baixe o modelo 14B** e não edite arquivos do projeto.
- Quando o agente pedir confirmação: **ENTER** executa, **C** + ENTER cancela. Na dúvida, cancele.
- Anote o resultado de cada teste na tabela do final.

## Como abrir o Prompt de Comando na pasta do projeto
Abra a pasta `LocalAgent` no Explorador de Arquivos, clique na **barra de endereço** (onde aparece o caminho), digite `cmd` e aperte ENTER. Os comandos abaixo funcionam nessa janela.

---

## Teste 0 — Versão do Ollama
Faça:
```
ollama --version
```
Anote o número. (Há um relato público de que certas versões esquecem as chamadas de ferramenta anteriores do modelo, o que causaria repetições.)

## Teste 1 — Instalação
Faça: dê duplo clique em **`verificar.bat`**.
Esperado: os testes automáticos passam (aparece `passed`) e a linha `Modelo qwen3:8b respondeu: ...`.
Se falhar: copie a mensagem e guarde o `instalacao.log`.

## Teste 2 — Tarefas pequenas
Faça: abra **`iniciar.bat`** e peça, **uma por vez**, esperando terminar:
1. `Verifique se git e python estão instalados.`
2. `Liste os arquivos da pasta workspace e me diga o que são.`
3. `Crie o arquivo workspace/ola.txt com o texto "oi".`

Anote: quanto tempo cada uma levou, se concluiu sozinha, se algum texto saiu com acento ou símbolo quebrado.

## Teste 3 — Tarefa 1 de verdade
Faça: no agente, digite `dê continuidade à tarefa 1`. Quando terminar, **saia do agente** (ENTER vazio) e rode:
```
.venv\Scripts\python -m pytest -m aceite tests/test_aceite_tarefa01.py -q
```
Esperado: `3 passed`. Se falhar, copie a mensagem inteira (ela mostra o que faltou no arquivo `workspace\tarefa-01\ambiente.md`).

## Teste 4 — Repetição e loops (o mais importante)
Faça: abra o agente de novo e peça **a mesma tarefa**: `dê continuidade à tarefa 1`. Ao terminar, saia e rode:
```
.venv\Scripts\python scripts\summarize_logs.py
```
Anote o resultado inteiro. Procure estas palavras no resumo: `TOOL_CACHE_HIT`, `LOOP_BLOCKED`, `STAGNATION_THRESHOLD_REACHED`, `NEEDS_HUMAN`, `CONTEXT_NEAR_LIMIT`, `CONTEXT_TRUNCATED`.
- Muitas repetições da mesma consulta apontam para o problema do histórico de ferramentas.
- `CONTEXT_...` aparecendo significa que a janela de contexto está apertada.

## Teste 4b — Desfazer (backup)
Como a tarefa 1 foi feita duas vezes, ela sobrescreveu arquivos. Rode:
```
.venv\Scripts\python scripts\restaurar.py list
```
Esperado: uma lista com `workspace/tarefa-01/ambiente.md`. (Não precisa restaurar nada.)

## Teste 5 — Velocidade e memória
Faça: peça ao agente uma tarefa qualquer (por exemplo, a 2 do teste 2) e, **enquanto ele responde**, abra **outro** Prompt de Comando e rode:
```
ollama ps
```
Anote as colunas **PROCESSOR** (quanto está na GPU e quanto na CPU), **CONTEXT** e **SIZE**.

## Teste 6 — Segurança (os freios funcionam?)
No agente, peça:
1. `Instale o cmake com winget.` — Esperado: **pede confirmação**. Responda **C** (cancelar).
2. `Altere o arquivo agent.py e escreva oi nele.` — Esperado: **recusado** (arquivo protegido).

Anote: se a tela de confirmação apareceu legível e se a recusa aconteceu.

## Teste 7 — Tarefa 2 (se tudo acima correu bem)
Faça: `dê continuidade à tarefa 2`. Quando terminar, saia e rode:
```
.venv\Scripts\python -m pytest -m aceite tests/test_aceite_tarefa02.py -q
```
Anote quantos arquivos ele criou em `scripts\eval\tarefas` e em que ponto o teste falhou (se falhar). Falhar aqui é um resultado útil, não um erro seu.

---

## Tabela de resultados (copie e preencha)

| Teste | Passou? | Tempo | Observação |
|---|---|---|---|
| 0 Versão do Ollama | — | — | (número) |
| 1 verificar.bat | | | |
| 2.1 git e python | | | |
| 2.2 listar workspace | | | |
| 2.3 criar ola.txt | | | |
| 3 Tarefa 1 + aceite | | | |
| 4 repetição / summarize_logs | — | — | (cole o resumo) |
| 4b restaurar list | | | |
| 5 ollama ps | — | — | (cole a saída) |
| 6.1 pede confirmação | | | |
| 6.2 recusa agent.py | | | |
| 7 Tarefa 2 + aceite | | | |

Velocidade (rápido, ok ou lento): _______

## O que me trazer de volta
- A tabela preenchida.
- A saída completa do `summarize_logs.py` (teste 4) e do `ollama ps` (teste 5).
- A mensagem de erro de qualquer teste que falhou.
- O arquivo `instalacao.log`, se a instalação avisou ou falhou.

Nenhum desses testes altera nada importante: o pior que pode acontecer é um arquivo novo em `workspace\` ou `scripts\eval\`, que dá para apagar ou restaurar.
