# Tarefas numeradas

Cada tarefa é um arquivo com objetivo, passos, o que pode mexer e um teste de aceite. Para o agente, basta dizer:

- `dê continuidade à tarefa 2`
- ou `@tarefa2`

O agente carrega o arquivo da tarefa, o seu pedido e o **progresso já salvo** em `workspace/tarefa-NN/progresso.md`, para retomar de onde parou.

| Nº | Tarefa | Quem | Antes | Teste de aceite |
|---|---|---|---|---|
| 01 | Verificar o ambiente e registrar | agente | nada | `pytest -m aceite tests/test_aceite_tarefa01.py -q` |
| 02 | Formato do conjunto de avaliação | agente | 01 (opcional) | `pytest -m aceite tests/test_aceite_tarefa02.py -q` |
| 03 | Programa que confere e pontua a avaliação | agente (melhor SMART) | 02 | `pytest -m aceite tests/test_aceite_tarefa03.py -q` |
| 04 | Medição no PC | você | instalação | você junta os dados |
| 05 | Decidir a configuração de modelos | você | 03 e 04 | `specs/avaliacoes.md` |

## Como saber se uma tarefa terminou
Rode o teste de aceite dela (coluna da direita) no Prompt de Comando, dentro da pasta do projeto:

```
.venv\Scripts\python -m pytest -m aceite tests/test_aceite_tarefa01.py -q
```

Se passar, a tarefa está concluída de verdade. Quem decide isso é o teste, não o que o modelo diz.

## Regras
- O agente não consegue alterar esta pasta nem os testes (são protegidos). Só você.
- Ele pode escrever em `workspace/` e, nas tarefas 02 e 03, em `scripts/eval/`.
- Para criar uma tarefa nova: copie um arquivo `tarefa-NN-*.md`, mude o número e o texto, e (se for do agente) escreva um teste `tests/test_aceite_tarefaNN.py` com `@pytest.mark.aceite`.
- Evite as palavras "continue", "desenvolvimento", "checklist" e "projeto.md" dentro dos arquivos de tarefa (elas acionam o fluxo antigo de desenvolvimento). Há um teste que confere isso.
