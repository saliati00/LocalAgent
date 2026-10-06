# Tarefa 02 — Formato do conjunto de avaliação

Quem faz: agente (o usuário revisa as tarefas de exemplo)
Pré-requisitos: tarefa 01 (opcional)
Tamanho: médio (10 a 20 ações)

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

## Passos
1. Crie `scripts/eval/FORMATO.md` explicando o formato acima em português, curto.
2. Crie 5 tarefas em `scripts/eval/tarefas/`, uma por arquivo, com dificuldades diferentes:
   - criar um arquivo com texto;
   - ler um arquivo do `setup` e gravar um resumo de uma linha;
   - listar uma pasta e gravar a contagem de arquivos;
   - criar um script Python que imprime um texto (aceite roda o script);
   - verificar uma ferramenta com `check_tools` e gravar o resultado.
3. Registre o progresso (veja abaixo) e responda com a lista de tarefas criadas.

## Pode criar/alterar
Somente `scripts/eval/` e `workspace/tarefa-02/`.

## Não faça
Não crie o programa que roda a avaliação (é a tarefa 03). Não use caminhos absolutos nem `..`.

## Pronto quando
`pytest -m aceite tests/test_aceite_tarefa02.py -q` passa.

## Se travar
Se o JSON ficar inválido duas vezes seguidas, pare e mostre o erro ao usuário.

## Progresso
Mantenha `workspace/tarefa-02/progresso.md`: uma linha por passo concluído (`[passo N] feito: ...`). Ao atualizar, releia o arquivo e reescreva-o inteiro com as linhas anteriores.
