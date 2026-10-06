# Tarefa 03 — Programa que confere e pontua a avaliação

Quem faz: agente (de preferência o modelo SMART, se existir)
Pré-requisitos: tarefa 02 concluída
Tamanho: médio (15 a 30 ações)

## Objetivo
Criar `scripts/eval/runner.py` com três funções puras (sem chamar modelo): carregar tarefas, conferir os critérios de aceite e resumir resultados. O teste de aceite já existe e define o comportamento exato.

## Funções que o teste exige
- `load_tasks(directory)` -> lista de dicts, lendo `*.json` em ordem alfabética.
- `check_acceptance(criteria, workdir)` -> `(bool, list[str])`: `True` se TODOS os critérios passam; a lista traz uma mensagem por critério que falhou.
  - `file_exists`: o caminho (relativo a `workdir`) existe.
  - `file_contains`: o arquivo existe e contém o texto.
  - `command_exit_zero`: roda o comando em `workdir` SEM shell (`shlex.split`, `subprocess.run`, timeout 60 s); passa se o código de saída for 0.
  - Caminho com `..` ou absoluto = critério falha (nunca lê nem escreve fora de `workdir`).
- `summarize(results)` -> dict. Cada resultado é `{"task_id": str, "passed": bool}` (vários por tarefa = várias rodadas). Retorna `{"total": int, "passed": int, "pass_rate": float, "by_task": {id: {"runs": int, "passed": int}}}`; `pass_rate` entre 0 e 1 (0 se não houver resultados).

## Passos
1. Leia `tests/test_aceite_tarefa03.py` (ele é a especificação).
2. Crie `scripts/eval/runner.py` com as três funções.
3. Rode `pytest -m aceite tests/test_aceite_tarefa03.py -q` e corrija até passar.
4. Registre o progresso (veja abaixo).

## Pode criar/alterar
Somente `scripts/eval/runner.py` e `workspace/tarefa-03/`.

## Não faça
Não altere os testes. Não chame o modelo dentro do runner. Não use `shell=True`.

## Pronto quando
`pytest -m aceite tests/test_aceite_tarefa03.py -q` passa.

## Se travar
Se o mesmo teste falhar 3 vezes com a mesma mensagem, pare, mostre a mensagem e peça ajuda ao usuário.

## Progresso
Mantenha `workspace/tarefa-03/progresso.md`: uma linha por passo concluído (`[passo N] feito: ...`). Ao atualizar, releia o arquivo e reescreva-o inteiro com as linhas anteriores.
