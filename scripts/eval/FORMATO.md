# Formato das tarefas de avaliação

Cada tarefa é um arquivo `.json` em `scripts/eval/tarefas/`. O programa `scripts/eval/runner.py` lê esses arquivos e confere, por código (sem nenhum modelo), se o trabalho ficou feito.

```json
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

## Campos
- `id` (obrigatório): nome curto e **único** da tarefa.
- `titulo` (obrigatório): descrição curta para humanos.
- `prompt` (obrigatório): o pedido exatamente como seria dado ao agente.
- `aceite` (obrigatório): lista de critérios. A tarefa só passa se **todos** passarem; uma lista vazia nunca conta como sucesso.
- `setup` (opcional): arquivos criados antes de rodar (caminho -> conteúdo).
- `max_iteracoes` (opcional): limite de iterações do agente para esta tarefa.

## Tipos de critério de aceite
- `file_exists`: o arquivo em `path` existe.
- `file_contains`: o arquivo em `path` existe e contém o `text`.
- `command_exit_zero`: roda o `command` na pasta de trabalho, **sem shell** (operadores como `&&` e `>` não funcionam), com limite de 60 s; passa se o código de saída for 0.

## Regras de segurança
Os caminhos são sempre relativos à pasta de trabalho. Caminho absoluto, com unidade (`C:`) ou com `..` faz o critério **falhar**: o programa nunca lê nem escreve fora da pasta.

## Como usar
- Conferir o estado atual: `python scripts/eval/runner.py` (imprime a taxa de sucesso).
- Resumir resultados já prontos: `python scripts/eval/runner.py --resultados resultados.json`.
