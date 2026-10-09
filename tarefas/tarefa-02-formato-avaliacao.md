# Tarefa 02 — Formato do conjunto de avaliação

Quem faz: agente (o usuário revisa as tarefas de exemplo)
Pré-requisitos: tarefa 01 (opcional)
Tamanho: médio (6 arquivos)

## Objetivo
Definir como cada tarefa de avaliação é escrita e criar 5 exemplos. Depois a tarefa 03 faz o programa que roda e pontua.

## Formato de uma tarefa de avaliação (um arquivo `.json`)
```
{
  "id": "arquivo-simples",
  "titulo": "Criar um arquivo de texto",
  "prompt": "Crie o arquivo workspace/eval/ola.txt com o texto oi.",
  "setup": {"workspace/eval/leiame.txt": "conteúdo inicial"},
  "aceite": [
    {"type": "file_exists", "path": "workspace/eval/ola.txt"},
    {"type": "file_contains", "path": "workspace/eval/ola.txt", "text": "oi"},
    {"type": "command_exit_zero", "command": "python --version"}
  ],
  "max_iteracoes": 10
}
```
- `setup` é opcional (arquivos criados antes de rodar). Caminhos sempre relativos, sem `..`.
- Tipos de aceite permitidos: `file_exists` (path), `file_contains` (path, text), `command_exit_zero` (command).
- Cada `id` precisa ser único.

## Arquivos a criar (nomes FIXOS)
Escreva cada arquivo UMA vez, com EXATAMENTE estes nomes. Se já existirem, sobrescreva o mesmo nome; nunca crie arquivos com outros nomes.
1. `scripts/eval/FORMATO.md`: explica o formato acima em português, curto.
2. `scripts/eval/tarefas/tarefa-01.json`: id `arquivo-simples`, criar um arquivo com texto.
3. `scripts/eval/tarefas/tarefa-02.json`: id `resumo-arquivo`, ler um arquivo do `setup` e gravar um resumo de uma linha.
4. `scripts/eval/tarefas/tarefa-03.json`: id `contar-arquivos`, listar uma pasta e gravar a contagem.
5. `scripts/eval/tarefas/tarefa-04.json`: id `script-python`, criar um script Python que imprime um texto (o aceite roda o script).
6. `scripts/eval/tarefas/tarefa-05.json`: id `verificar-ferramenta`, verificar uma ferramenta com `check_tools` e gravar o resultado.

## Passos
1. Crie os 6 arquivos acima, um por vez, sem reescrevê-los.
2. Registre o progresso (veja abaixo).
3. Responda "concluí". O Harness roda o teste de aceite sozinho; se falhar, ele mostra o que faltou e você corrige SÓ aquilo.

## Pode criar/alterar
Somente `scripts/eval/` e `workspace/tarefa-02/`.

## Dica
`write_file` já cria as pastas que faltarem (`scripts/eval/tarefas/` inclusive): não precisa de `mkdir`.

## Não faça
Não crie o programa que roda a avaliação (é a tarefa 03). Não use caminhos absolutos nem `..`. Não regrave arquivos que já estão certos.

## Pronto quando
`pytest -m aceite tests/test_aceite_tarefa02.py -q` passa.

## Se travar
Se o mesmo erro aparecer 2 vezes seguidas, pare e mostre o erro ao usuário.

## Progresso
Mantenha `workspace/tarefa-02/progresso.md`: uma linha por passo concluído (`[passo N] feito: ...`). Ao atualizar, releia o arquivo e reescreva-o inteiro com as linhas anteriores.
