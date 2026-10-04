# Skill: Desenvolvimento Autônomo do Projeto

## Objetivo

Orientar o agente local sobre como assumir o desenvolvimento do projeto `local-agent`, lendo a especificação em `specs/projeto.md`, identificando a pendência atual, planejando, implementando alterações reais, executando testes automatizados, validando e atualizando a especificação.

---

## Princípio Fundamental

> Não faça apenas planos ou explicações teóricas. Realize trabalho concreto no código e valide com testes.

Uma tarefa de desenvolvimento só é considerada avançada quando:
1. Os arquivos foram inspecionados;
2. As mudanças no código ou arquivos foram realizadas (via `replace_in_file` ou `write_file`);
3. Os testes automatizados foram executados (via `run_command` com `pytest`);
4. Os testes passaram sem erros;
5. O item correspondente na especificação `specs/projeto.md` foi atualizado de `* [ ]` para `* [x]`.

---

## Procedimento Passo a Passo

### 1. Entender o Estado Atual
- Consulte o resumo do projeto fornecido pelo Harness ou use `extract_project_progress`.
- Identifique a fase atual e a **próxima ação pendente** (`next_action`).
- Não tente implementar várias fases ao mesmo tempo. Foque na pendência imediata.

### 2. Inspecionar o Código Existente
- Antes de criar ou modificar qualquer arquivo, verifique se ele já existe usando `list_directory` ou `read_file`.
- Se o arquivo for grande, use `read_file` com `start_line` e `end_line` para inspecionar apenas a seção relevante.
- Não recrie módulos ou funções que já estão implementados e funcionando.

### 3. Implementar a Solução
- Para editar arquivos existentes, prefira sempre `replace_in_file` fornecendo linhas de contexto para garantir unicidade.
- Só use `write_file` para criar novos arquivos ou quando uma reescrita completa for deliberadamente necessária.
- Nunca grave código com `TODO` ou implementações falsas para "passar de fase". O código deve ser real e funcional.

### 4. Executar e Validar com Testes
- Execute os testes automatizados com:
  `run_command(command="pytest -v", reason="Validar mudancas implementadas")`
  (O ambiente do Harness já configura o caminho correto do virtualenv).
- Se algum teste falhar:
  1. Leia a mensagem de erro (stderr/stdout);
  2. Identifique o arquivo e a linha onde ocorreu a falha;
  3. Corrija o código usando `replace_in_file`;
  4. Execute os testes novamente até que todos passem.

### 5. Atualizar a Especificação
- Quando a funcionalidade estiver testada e aprovada:
  - Localize o item em `specs/projeto.md`;
  - Atualize a linha de `* [ ] <item>` para `* [x] <item>` usando a ferramenta apropriada ou `replace_in_file`.

### 6. Relatar o Resultado
- Informe claramente:
  - O que foi implementado;
  - Quais arquivos foram criados ou modificados;
  - O resultado dos testes automatizados (quantos passaram);
  - A confirmação de atualização do checklist;
  - Qual é a próxima pendência do projeto.
