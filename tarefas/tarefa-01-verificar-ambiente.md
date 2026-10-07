# Tarefa 01 — Verificar o ambiente e registrar

Quem faz: agente (o usuário confere o resultado)
Pré-requisitos: nenhum
Tamanho: pequeno (5 a 8 ações)

## Objetivo
Descobrir o que está instalado neste PC e gravar um resumo curto. Serve de primeiro teste real do agente e registra a versão do Ollama.

## Passos
1. Use `check_tools` UMA vez com: git, python, ollama, nvidia-smi, cmake.
2. Para cada ferramenta encontrada, rode `run_command` com `<ferramenta> --version` (para `nvidia-smi` rode só `nvidia-smi`).
3. Crie `workspace/tarefa-01/ambiente.md` com EXATAMENTE estas linhas (uma por ferramenta, valor curto, ou `não encontrado`):
```
# Ambiente
- python: <versão>
- git: <versão>
- ollama: <versão>
- nvidia-smi: <modelo da placa ou não encontrado>
- cmake: <versão ou não encontrado>
```
4. Registre o progresso (veja abaixo) e responda com um resumo de 3 linhas. O Harness então roda o teste de aceite sozinho.

## Pode criar/alterar
Somente `workspace/tarefa-01/`.

## Não faça
Não instale nada. Não use `winget`, `pip install` nem `sudo`.

## Pronto quando
`pytest -m aceite tests/test_aceite_tarefa01.py -q` passa.

## Se travar
Se uma ferramenta pedir confirmação ou falhar duas vezes, pare e diga o que o usuário deve fazer.

## Progresso
Mantenha `workspace/tarefa-01/progresso.md`: uma linha por passo concluído (`[passo N] feito: ...`). Ao atualizar, releia o arquivo e reescreva-o inteiro com as linhas anteriores.
