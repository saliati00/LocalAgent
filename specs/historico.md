# Histórico do projeto (rodadas, evidências e decisões)

Capítulos movidos de `specs/projeto.md` em 09/10/2026 para deixar a especificação só com o plano em vigor e o checklist. A numeração foi mantida para que as referências antigas continuem valendo. O resumo do que está em vigor fica no capítulo 39 de `specs/projeto.md`, que prevalece em caso de conflito.

# 39. EVIDÊNCIAS DOS LOGS (02 a 03/10/2026)

Análise de `logs/agent.log` (56 execuções; 7 são testes automatizados, restando 49 execuções reais).

* Tarefas pequenas e fechadas (verificar um arquivo, criar `calc.py` com teste, pesquisar uma URL) concluem em 1 a 3 iterações.
* Cerca de 25 execuções de "Continue o desenvolvimento..." terminaram em cancelamento, no limite de 31 iterações ou em loop.
* Quatro execuções seguidas (03/10, 18:50 a 19:14) bateram 31 iterações com 0 a 2 falhas, repetindo leituras (`get_model_registry` de 7 a 12 vezes, `get_project_status`, `get_memory`) sem produzir nada.
* A tarefa `sudo dnf install git` gastou 31 iterações repetindo "preciso da senha". Nem o modelo nem o Harness entendiam "bloqueado, parar e esperar o humano".
* A verificação de ambiente fez 24 a 29 chamadas `command -v X`, uma por ferramenta.
* **Contexto estourado:** 144 de 406 chamadas reais ao modelo (35%) usaram 7000 ou mais tokens de uma janela de 8192 (máximo 8173, média 4873). Acima do `num_ctx` o Ollama descarta o início da conversa, inclusive o objetivo.
* Em tarefas de desenvolvimento o prompt carregava as Skills `development`, `environment` e `models`: cerca de 15,5 mil caracteres (~5 mil tokens), mais da metade da janela.
* O juiz de conclusão (um LLM) registrou `DONE` em etapas que falharam (ex.: "registrada no checklist: 'web_search falhou'").
* Cada resposta de texto dispara uma chamada extra ao modelo ativo para o juiz de conclusão.
* Nestes logs, nenhuma execução mostra o agente local construindo um componente real do projeto. O único código criado foi `scripts/calc.py` com um teste.

Conclusão: o gargalo não é falta de componentes, é contexto, critério de "pronto" e falta de medição. As medidas adotadas estão nos capítulos 41 a 44 e na FASE 11 do checklist.

---

# 40. LIMITES REALISTAS DO HARDWARE

Valores marcados como estimativa devem ser confirmados por medição (FASE 11).

* Hardware de referência: ver `specs/ambiente.md` (Ryzen 5 5600G, RTX 3070 8 GB, 16 GB de RAM).
* Um modelo de ~8B em Q4 cabe inteiro na VRAM (~5,5 GB observados) e responde rápido.
* Um modelo de ~14B em Q4 (~9 GB) exige offload parcial para a RAM. Estimativa: de poucos tokens/s a ~10 tokens/s, adequado para uso curto e pontual, não para operar em loop.
* Modelos de 20B ou mais não são úteis como "HEAVY" neste hardware. A Fase 8 deve confirmar isso manualmente, sem automação.
* O KV cache é específico de cada modelo e **não pode ser compartilhado** entre FAST e SMART. Cada troca de modelo recarrega os pesos e reprocessa o prompt inteiro. Por isso a escalada deve ser rara, curta e começar de um resumo (capítulo 41).
* Quantizar modelos localmente não é prático (um 14B em fp16 tem ~28 GB). Usar GGUFs já quantizados.
* "Usar toda a RAM disponível" (capítulo 3) é arriscado com 16 GB e Windows em uso.
* Upgrade de melhor custo-benefício: 32 GB de RAM. Ele não acelera um 14B denso, mas abre modelos MoE, que rodam bem melhor em CPU/RAM.
* Tamanho de contexto: manter `NUM_CTX` conservador e o prompt abaixo de ~60% da janela (medido por `PROMPT_SIZES`).

---

# 41. FAST + SMART: COMPORTAMENTO IMPLEMENTADO

O FAST opera e conversa; o SMART é um consultor curto, não um segundo operador permanente.

* FAST é o padrão. A escalada é reativa: 3 erros consecutivos, ou 18 iterações com mais de 5 falhas, ou 6 ciclos de estagnação.
* Ao escalar, o detector de estagnação é reiniciado e o SMART recebe um **pacote de passagem** montado pelo Harness (`core/harness/handover.py`, até 3500 caracteres): objetivo, motivo, fase, pendência, ações já concluídas, últimos resultados de ferramentas e erros recentes. Ele **não** herda o histórico (e os loops) do FAST.
* O SMART tem tempo limitado: volta ao FAST quando destrava a etapa (progresso real) ou depois de `SMART_MAX_ITERATIONS` (8) iterações, também com um pacote de passagem.
* Mais de `MAX_ESCALATIONS` (3) escaladas, ou um SMART que também estagna, terminam em `needs_human`.
* Estados terminais distintos: `completed`, `cancelled` (o usuário recusou), `needs_human` (depende de uma ação do usuário), `blocked`, `failed` e `smart_unavailable`.
* Três respostas de texto praticamente iguais seguidas (similaridade de 0,9 ou mais) terminam em `needs_human`.
* Ferramentas de leitura (`get_model_registry`, `get_project_status`, `get_memory`, `read_file`, `list_directory`, `check_tools`, `load_skill`) são memoizadas por tarefa e o cache é invalidado por qualquer ferramenta que altere estado. A ferramenta `check_tools` verifica N executáveis numa só chamada.
* O prompt tem orçamento: as Skills ocupam até `SKILLS_BUDGET_CHARS` (3500 caracteres); o excedente entra como índice e o modelo lê o resto com `load_skill`.
* Cada linha de log carrega o `run_id`, e cada tarefa registra `PROMPT_SIZES` (tamanho por seção do prompt).

Pendências desta arquitetura (FASE 11):

* Prefixo do prompt estável (sem timestamps) para aproveitar o cache de prefixo do Ollama. Não medido.
* Avaliar um SMART da mesma família do FAST (por exemplo, um 14B da família Qwen3, se disponível) e o próprio FAST com `think=True` como baseline, em vez de assumir `qwen2.5-coder:14b`.
* O `llama-server` (llama.cpp) permite salvar e restaurar o KV de um slot em disco; avaliar isso como motivo concreto para a Fase 3. O Ollama não expõe isso.
* Substituir o juiz de conclusão por LLM por critério de aceite executável (capítulo 44).

---

# 42. AUTOEXPANSÃO SEGURA

O agente pode se expandir **criando Skills** (texto, sem execução). Ele **nunca** altera o Harness, as permissões, os testes nem Skills ativas.

Fluxo: `rascunho` → `revisão humana` → `ativa` (mesma lógica de "descoberta ≠ adoção" dos modelos).

1. Só o modelo SMART pode propor, com a ferramenta `propose_skill`. O FAST recebe uma recusa do Harness.
2. O rascunho é gravado em `skills_pending/<nome>/SKILL.md`, gerado por código a partir de campos estruturados (nome, descrição, gatilhos, quando usar, passos, como validar, limites, tools). Rascunhos nunca são carregados nem casados com tarefas.
3. O validador (`core/skills/validator.py`) recusa: nome inválido, mais de 2400 caracteres, descrição acima de 160, menos de 1 ou mais de 12 gatilhos, tools inexistentes, seções obrigatórias ausentes e trechos que enfraquecem regras (ignorar regras/restrições, desativar confirmação, "sem confirmação" quando afirmativo, `allow_install`/`allow_system_changes`/`allow_destructive`, `| sh`, `iex`). Negações ("Não baixa nada sem confirmação") são aceitas.
4. O Harness, não o modelo, informa `used_web`. Skills de tarefas que usaram `web_search`, `fetch_url` ou `download_file` pedem confirmação extra na promoção (risco de prompt injection).
5. A promoção é humana: `python scripts/promote_skill.py list | show | promote | reject`. Promover exige terminal interativo e digitar o nome; a validação roda de novo. Rejeitados vão para `skills_pending/_rejected/`.
6. `skills/` e `skills_pending/` são protegidos contra `write_file`, `replace_in_file` e `download_file`.
7. Gatilhos de Skills novas vêm do cabeçalho da própria Skill. As nativas continuam usando `core/skills/loader.py`.
8. Sugestão de uso: criar uma Skill depois de um procedimento que funcionou de verdade em duas ou mais tarefas, ou quando uma tarefa falhou por falta de conhecimento. Cada promoção deve virar um commit.

Próximos degraus (não implementados): scripts auxiliares dentro de uma Skill, sempre executados por `run_command` com confirmação; ferramentas novas em `tools/plugins/` somente com sandbox e testes escritos pelo usuário. O Harness fica fora de todos os degraus.

Pendência: a memória persistente (`save_memory`) também entra no prompt e hoje não tem limite nem revisão. Aplicar limite de tamanho e revisão das entradas de decisão.

---

# 43. ESCOPO REVISADO

Esta tabela orienta o que o agente e o usuário devem priorizar. O agente **não deve iniciar** itens marcados como cortados ou adiados.

| Bloco | Decisão | Motivo |
|---|---|---|
| Harness, permissões, Task State, Skills | Manter e estabilizar | Já existem; o problema é contexto e critério de pronto |
| FAST + SMART com passagem de resumo | Manter | Capítulo 41 |
| Comparar llama.cpp com Ollama (Fase 3) | Adiar | Só se o Ollama não atender (ver o ponto do KV em disco no capítulo 41) |
| Benchmark de contexto automatizado | Adiar | Medição manual basta para este hardware |
| Model Scout automático (Fase 7) | Cortar | O universo útil em 8 GB de VRAM é pequeno; escolha manual |
| Quantização local própria | Cortar | Usar GGUFs prontos |
| Descobrir o teto do hardware (Fase 8) | Fazer manualmente | Uma tarde de testes |
| Interface web (Fase 9) | Reaproveitar uma existente | Cap. 2.4; reavaliar Open WebUI e, com o 14B, OpenCode/Aider |
| GUI, visão e automação de mouse (Fase 10) | Cortar | Fora do alcance de modelos de 8B a 14B locais |
| Autoexpansão | Somente Skills, com revisão humana | Capítulo 42 |

---

# 44. DEFINIÇÃO DE PRONTO E ORGANIZAÇÃO

* Cada item novo do checklist deve declarar **"pronto quando: <comando verificável>"**. Meta: o Harness marcar `[x]` quando o comando retornar 0, no lugar do juiz por LLM. Hoje o gate de aceitação cobre só alguns itens (seleção de candidato SMART e relacionados).
* Tarefas de desenvolvimento devem ser **unidades pequenas e test-first**: objetivo, arquivos permitidos e um comando de aceite; o usuário escreve o teste e o agente implementa até ficar verde.
* O checklist permanece neste arquivo porque o Harness lê `specs/projeto.md`. O hardware e o ambiente ficam em `specs/ambiente.md`, para serem atualizados ao trocar de máquina.
* A FASE 11 (estabilização) foi posicionada antes da FASE 2 de propósito: o Harness escolhe a próxima pendência pela ordem do arquivo. A numeração não foi alterada para não quebrar nomes usados pelo Harness.
* Operação no Windows: `instalar.bat`, `verificar.bat`, `iniciar.bat` e `LEIA-ME-WINDOWS.md`.
* Decisões em aberto: quem promove Skills (hoje, só o usuário); política de memória; escolha do candidato SMART por medição; quando publicar estas alterações no GitHub.

---

# 45. LIÇÕES DE PROJETOS PARECIDOS (pesquisa de 06/10/2026)

Pesquisa feita por agentes de busca; as fontes não foram reabertas uma a uma. Itens marcados como hipótese precisam ser medidos antes de virar regra.

Confirmado por fontes primárias (docs, READMEs, issues, papers):

* Prompts grandes derrubam agentes com modelo local: o Cline criou um "compact prompt" (~10% do normal) e o Roo Code desistiu de suportar prompt grande; o OpenHands pede 22 a 32k de contexto.
* O Ollama pode truncar o início da conversa em silêncio quando o prompt passa do `num_ctx` (relatos no Goose e em issues de terceiros). Com `ollama.chat` na API nativa o `num_ctx` informado vale.
* Tool calling é o gargalo dos modelos abertos pequenos (Goose: 14B ficaram 50% ou mais piores que um modelo de ponta).
* Juízes LLM de "concluído" erram muito (arXiv 2606.09863): 45 a 48% das falhas são falso sucesso; com verificação independente cai para ~3%.
* Detector de travamento do OpenHands: mesma ação com erro 3 vezes, alternância A-B por 6 ciclos, mesma ação e observação 4 vezes.
* Skills públicas têm risco real (Snyk, fev/2026: 36,8% de 3.984 Skills com falha).

Hipóteses a medir:

* Issue do Ollama #14601 (mar/2026): com `qwen3:8b` e o parâmetro `tools`, tool calls anteriores do assistente somem do histórico, o que explicaria loops de repetição. Registrar a versão do Ollama no PC alvo.
* `OLLAMA_FLASH_ATTENTION=1` com `OLLAMA_KV_CACHE_TYPE=q8_0` para subir o contexto para 12 a 16k; efeito na precisão de tool calling não medido.
* Expor de 5 a 8 tools por turno: implementado (capítulo 47); falta medir se o roteamento por palavras erra em tarefas reais.
* Formato de edição `whole` para arquivos pequenos (um relato mostrou 0 para 100 de acerto ao trocar de `diff`).
* Escrita compacta de prompts, schemas e Skills (menos tokens por instrução) como alternativa a cortar conteúdo.

Já implementado a partir desta pesquisa:

* Detector de travamento com os limiares acima (`core/harness/stagnation.py`).
* Detecção de truncamento do contexto pelo `prompt_eval_count` (`CONTEXT_NEAR_LIMIT` e `CONTEXT_TRUNCATED` no log, com compactação forçada).
* Teto de saída em `read_file` (8000 caracteres) e `list_directory` (200 itens), com aviso para usar `start_line` e `end_line`.
* Validação de sintaxe Python em `write_file` e `replace_in_file`: a escrita inválida é recusada e o arquivo não muda.
* Validador de Skills recusa Unicode invisível, trechos base64 e URLs em rascunhos.

Ainda não implementado: substituir o juiz de conclusão, conjunto de avaliação, escrita compacta de prompts (inglês/telegráfico) e a comparação com harnesses prontos (Aider) na avaliação.


---

# 46. TAREFAS NUMERADAS, CONSOLE E ORÇAMENTO DE PROMPT

Achados de uma simulação de clone limpo (06/10/2026), já corrigidos:

* **Tarefas numeradas:** `tarefas/tarefa-NN-*.md` define objetivo, passos, o que pode mexer, "pronto quando" e onde salvar o progresso. O usuário diz "dê continuidade à tarefa 2" (ou `@tarefa2`); o Harness carrega o roteiro, o pedido e o progresso salvo em `workspace/tarefa-NN/progresso.md`. A pasta `tarefas/` e os testes de aceite são protegidos: só o usuário os altera. Os testes de aceite usam o marcador `aceite` (fora da suíte normal; rodar com `pytest -m aceite <arquivo>`), e quem decide se a tarefa terminou é o teste, não o modelo. Uma tarefa numerada não aciona o fluxo de desenvolvimento do checklist.
* **Console do Windows:** um `print` com "→", "✓" ou emoji derrubava o agente em console cp1252/cp850 (inclusive a tela de confirmação). Corrigido com `core/console.py` (`safe_print`, `ensure_utf8_console`) e `chcp 65001` + `PYTHONUTF8=1` nos `.bat`.
* **Prompt fixo acima da janela:** uma tarefa numerada estimava 8363 tokens para 8192 (102%) antes de qualquer conversa. Medidas: system prompt compacto para tarefas numeradas (resumo do checklist fora e Skills só como índice), memória persistente limitada a 1500 caracteres (entradas mais recentes primeiro), orçamento de Skills de 3500 caracteres, descrições do schema de tools abreviadas, regras mais curtas. Resultado estimado na época: tarefa numerada 53%, tarefa simples ~60% e desenvolvimento ~70% da janela (superado pelo capítulo 47: 30%, 28% e 65%) (estimativa de 3 caracteres por token; confirmar com `PROMPT_SIZES`). O Harness registra `PROMPT_TOO_BIG` quando o prompt fixo passa de 70%.
* **Proteções adicionais:** os scripts que o usuário executa (`scripts/promote_skill.py`, instalador e `.bat`) e os `requirements*.txt` ficaram fora do alcance das tools do agente.
* **Tempo e velocidade nos logs:** cada linha `TOKENS` registra `seconds` (tempo da chamada) e `tok_s` (tokens por segundo gerados, usando o `eval_duration` do Ollama quando disponível); `scripts/summarize_logs.py` mostra média, mínimo e máximo. Ctrl+C no terminal interrompe só a tarefa atual (`INTERRUPTED` no log).
* **Roteiro de testes no PC alvo:** `ROTEIRO-DE-TESTES.md` descreve a primeira rodada de testes do usuário (instalação, tarefas pequenas, tarefa 1 com aceite, repetição e loops, velocidade, segurança e tarefa 2) com tabela de resultados; a tarefa 04 aponta para ele.
* **Resumo de logs:** `scripts/summarize_logs.py` consolida `PROMPT_SIZES`, tokens, avisos de contexto, escaladas e `needs_human`.


---

# 47. HARNESS ENXUTO: TOOLS POR PERFIL, BUSCA E BACKUP

Pesquisa de 06/10/2026 sobre harnesses usados com modelos locais: nenhum harness popular cabe de forma confortável em 8k de contexto. OpenCode usa ~7,5 mil tokens só no primeiro turno (um blog, versão 1.18), OpenHands pede 22k ou mais e Goose pede 8k a 32k. A Cline criou um prompt compacto e mesmo assim relatos da AMD dizem que modelos abaixo de ~30B falham com ela. A recomendação da comunidade para contexto curto é o estilo minimalista (poucas tools, prompt abaixo de ~1k tokens), que é o que este harness segue. Decisão: **manter o harness próprio, enxuto, e roubar ideias** do Aider, mini-SWE-agent e pi, sem adotá-los. (Parte das fontes não foi aberta pessoalmente; ver capítulo 45.)

Implementado:

* **Tools por perfil.** O schema de tools entra em toda chamada e era o maior bloco fixo do prompt. Agora o modelo vê só o grupo `base` (8 tools: `list_directory`, `read_file`, `write_file`, `replace_in_file`, `run_command`, `search_files`, `check_tools`, `load_skill`). Os demais grupos aparecem conforme a tarefa:
  * `web` (`web_search`, `fetch_url`, `download_file`): pedido com pesquisa, internet, URL, download, GitHub...
  * `memory` (`save_memory`, `get_memory`): pedido que fala de memória; sempre no fluxo de desenvolvimento.
  * `project` (`update_spec_checklist`, `get_project_status`): fluxo de desenvolvimento ou pedido que cita checklist/pendência.
  * `models` (registry, candidato, adoção do SMART): pedido ou fase que trata de modelos.
  * `skills_authoring` (`propose_skill`): somente o SMART.
  O system prompt lista pelo nome as tools que estão fora do schema. Se o modelo chamar uma delas, o Harness ativa o grupo (log `TOOL_GROUP_ENABLED`) e ela passa a aparecer no schema. A ordem dos grupos é fixa para ajudar o cache de prefixo. O dispatch continua completo: perfis controlam só o que gasta contexto, não permissões.
* **`search_files`** (somente leitura): procura texto nas linhas dos arquivos do projeto (sem diferenciar maiúsculas), com filtro de nome (`glob`) e pasta (`path`); sem texto, lista arquivos por nome. Restrita ao projeto, ignora `.git`, `.venv`, `__pycache__`, logs, backups e arquivos binários ou grandes, e devolve no máximo 30 resultados curtos (limite 50), com aviso quando há mais.
* **Backup automático.** Antes de `write_file` ou `replace_in_file` sobrescrever um arquivo existente, o Harness guarda a versão anterior em `backups/<data-hora>/<caminho>` (arquivos até 2 MB; mantém as 300 pastas mais recentes). O agente não tem tool para restaurar e não escreve em `backups/`. Quem desfaz é o usuário: `python scripts/restaurar.py list` e `python scripts/restaurar.py restore "<id>"` (restaurar também guarda a versão atual).
* **Prompt compacto** também para tarefas simples: o resumo do checklist e as regras longas só entram no fluxo de desenvolvimento.
* **Resultado medido (estimativa de 3 caracteres por token):** schema do grupo base ~885 tokens (antes ~2,9 mil com todas as tools). Prompt fixo estimado: tarefa numerada ~30% da janela de 8192, tarefa simples ~28% e desenvolvimento ~65%.

Pendências deste capítulo: medir em tarefas reais se o roteamento por palavras-chave erra (uma tool escondida chamada sem argumentos gera uma falha antes de o grupo ser ativado); formato de edição `whole` para arquivos pequenos; comparar com o Aider na avaliação da FASE 11.


---

# 48. PRIMEIRA RODADA REAL (log de 06/10/2026, analisado em 07/10)

Primeiro log de execução no PC alvo (Windows, RTX 3070 8 GB, Qwen3 8B no Ollama): 9 execuções, 89 chamadas ao modelo. Números medidos:

* **Velocidade:** média de 61,6 tokens/s na geração (mín 53,3, máx 72,3). Tempo médio por chamada de 4,5 s (máx 15,3 s). O 8B Q4 roda inteiro na GPU e o hardware não é o gargalo.
* **Tokens reais do prompt:** o Ollama contou ~0,82 do estimado (cerca de 3,65 caracteres por token); a estimativa de `CHARS_PER_TOKEN` foi recalibrada de 3,0 para 3,6. O prompt fixo real ficou entre 1,4 mil e 2,8 mil tokens (17% a 34% da janela de 8192).
* **Contexto:** um único `CONTEXT_NEAR_LIMIT` (7845 tokens), na tarefa 02, quando o histórico acumulou muitas gravações de arquivos grandes.
* **Tarefas pequenas:** verificar ferramentas, listar pasta, criar arquivo e pesquisar na web concluíram em 1 chamada de ferramenta cada.

Falhas observadas e correções:

* **O juiz de conclusão por LLM errou.** Na tarefa 02 o agente criou os 6 arquivos pedidos e disse que concluiu; o juiz respondeu que "FORMATO.md não foi criado" (falso). O agente regravou tudo 3 vezes e bateu o limite de 31 iterações. Correção: nas tarefas numeradas o **Harness roda o teste de aceite** (até 3 tentativas, com a saída do teste devolvida ao modelo) e só ele decide; esgotadas as tentativas, termina em `needs_human`.
* **Regravar o mesmo arquivo contava como progresso**, então o detector de estagnação nunca disparava. Correção: mais de 3 gravações no mesmo caminho na mesma tarefa deixam de contar como progresso.
* **Tarefa do usuário executada pelo agente.** A tarefa 04 é um roteiro humano, mas o agente a executou por 8 minutos: rodou `verificar.bat` várias vezes e, em duas chamadas, **adotou um SMART no registry sem nenhum benchmark** (a regra exigia só o status "selecionado para benchmark"). Correções: tarefas cujo "Quem faz" é o usuário são recusadas pelo Harness; registrar, selecionar e adotar modelos agora exigem confirmação do usuário.
* **Tarefa 02 repetida duplicou ids** (arquivos de outra rodada com o mesmo id), e o agente tentou "consertar" trocando um trecho por ele mesmo. Correção: a tarefa agora fixa os nomes dos arquivos (sobrescrever em vez de criar outros).
* **Código Python com quebra de linha dentro de string** (tarefa 03): a validação de sintaxe recusou o arquivo duas vezes (funcionou), mas o modelo não entendeu o motivo. Correção: a mensagem de erro agora mostra a linha e explica `\n` e as aspas triplas; a tarefa avisa que `replace_in_file` só edita arquivos existentes.
* **`cat` no Windows:** o modelo tentou `cat` e recebeu um erro genérico. Correção: a mensagem agora aponta `read_file`, `list_directory` e `search_files`.
* **Ainda não testados na rodada real:** tarefa 01, segurança (confirmação e arquivo protegido), repetição da tarefa 01, `@iniciar-desenvolvimento` e o backup.

Resultado da tarefa 02: duas execuções, nenhuma concluiu (limite de iterações; escalada para um SMART inexistente). Da tarefa 03: o 8B não conseguiu escrever o `runner.py` (dois erros de sintaxe e uma tentativa de editar arquivo inexistente). Isso é coerente com o esperado para o 8B em código; a tarefa 03 deve ser tentada com um SMART.


---

# 49. BATERIA AUTOMÁTICA DE TESTES NO PC ALVO

Testar uma coisa por dia não escala. `scripts/bateria.py` roda uma bateria inteira sem teclado e devolve um único relatório. Ela é chamada pelo `comparar.bat` (capítulo 50), a única porta de entrada para o usuário; rodar um só modelo é `comparar.bat --modelos <modelo>`.

* **Isolamento:** cada caso roda em um processo separado, com `stdin` fechado (toda confirmação é cancelada) e tempo limite (15 min; 25 min nos casos lentos).
* **Veredito objetivo:** cada caso tem uma conferência de arquivo, de resposta ou de estado, nunca um juiz LLM. Em TODOS os casos o script compara o hash de arquivos protegidos (`agent.py`, `core/paths.py`, `core/tasks.py`, `core/harness/permissions.py`, `tests/conftest.py`, `models/registry.json`); qualquer mudança é uma violação grave, mesmo que o caso tenha passado.
* **Cobertura:** 11 casos simples (nove repetidos para medir consistência), 6 de raciocínio (contas de um e dois passos, regra de desconto, maior valor, contagem de linhas, multiplicação entre dois arquivos; repetidos 2 vezes, resposta numérica exata), 8 de segurança (instalação, arquivo protegido, troca de modelo, apagar pasta, comando perigoso, ordem escondida em arquivo, tarefa do usuário), 1 de comportamento e 6 de tarefas numeradas (a tarefa 3 e o desenvolvimento geral só como informação).
* **Efeitos colaterais:** `memory/store.json`, `models/registry.json` e `specs/projeto.md` são restaurados ao final, e o `git status` do fim entra no relatório.
* **Relatório:** `logs/bateria/<data>/RELATORIO.md` (resultado por grupo e por execução, eventos do Harness somados, velocidade, `ollama ps`) mais a transcrição de cada caso.
* **Limite conhecido:** a verificação da resposta textual (por exemplo, "admitiu que o arquivo não existe") é por palavras; serve para triagem, não para prova.


---

# 50. COMPARAÇÃO DE MODELOS FAST

Pesquisa feita em 07/10/2026 (Hugging Face, Ollama e fontes da web) mostrou que o `qwen3:8b` está uma geração atrás: o **Qwen3.5** (fev/2026) existe no Ollama em 0.8b, 2b, 4b, 9b, 27b, 35b e 122b, com contexto de 256K, entrada de imagem e treino declarado para agentes. Os números do fabricante para o 9B são BFCL-V4 66,1, TAU2-Bench 79,1 e LiveCodeBench v6 65,6. Dois pontos de cautela: (1) os ganhos de ranking são medidos com raciocínio ligado e o agente usa `think=False`; (2) o 9b ocupa de 6,6 a 7,6 GB e pode vazar da GPU de 8 GB para a CPU, enquanto o 4b (3,3 a 4 GB) cabe com folga. A conclusão sobre o Qwen2.5-Coder 7B (set/2024) foi descartá-lo por idade.

Em vez de decidir por ranking, o projeto mede:

* **`comparar.bat` / `scripts/comparar_modelos.py` (única porta de entrada, sem opções roda os três modelos do zero):** roda a MESMA bateria (capítulo 49) em cada modelo e gera `logs/comparacao/<data>/COMPARATIVO.md` (aprovação por modelo, por grupo e por caso, velocidade, eventos do Harness, violações e `ollama ps`).
* **Troca sem tocar no registry:** a variável de ambiente `LOCALAGENT_FAST_MODEL` sobrescreve o FAST apenas na execução (`ModelRouter.get_fast_model`).
* **Teste rápido por modelo:** uma chamada real com `think=False` e uma ferramenta de teste; modelo que não responde ou não aceita ferramentas é pulado com o motivo, sem derrubar a comparação.
* **Rodada-base reaproveitada:** `--base <pasta>` usa uma bateria já feita com o `qwen3:8b` como primeira coluna.
* **Visão geral no terminal:** ao final, uma tabela de texto com um modelo por linha (casos ok e falhos, erros de ferramenta, tokens de entrada e saída, tokens/s, minutos), também gravada no topo do COMPARATIVO.md. Os totais de tokens vêm das linhas `TOKENS` do log de cada caso.
* **Critério de escolha (impresso no relatório):** maior aprovação nos casos que contam; descartar quem violar arquivo protegido, ficar abaixo de 15 tokens/s ou aparecer com CPU no `ollama ps`; em empate, o mais rápido.
* **Download:** os modelos que faltam são listados com o tamanho e só são baixados após confirmação (S/N) do usuário.


---

# 51. PRIMEIRA COMPARAÇÃO REAL DE MODELOS (07/10/2026)

Primeira execução do `comparar.bat` no PC alvo (Ollama 0.40.0, RTX 3070 8 GB): `qwen3:8b`, `qwen3.5:9b` e `qwen3.5:4b`, 32 execuções contáveis cada. Os três couberam 100% na GPU (5,6 GB, 5,6 GB e 3,1 GB). A bateria inteira levou cerca de 30 minutos, bem menos que os 1 a 1,5 hora por modelo estimados antes.

| Modelo | Aprovação | tokens/s | Erros de ferramenta | Minutos |
|---|---|---|---|---|
| qwen3:8b | 29/32 (91%) | 68,7 | 20 | 9,3 |
| qwen3.5:9b | 27/32 (84%) | 51,1 | 27 | 11,2 |
| qwen3.5:4b | 27/32 (84%) | 98,9 | 33 | 8,6 |

Grupos simples (18/20 nos três) e segurança (8/8 nos três, 0 violações de arquivos protegidos) empataram. A diferença está em `tarefas` (8b 3/4; 9b e 4b 1/4), mas a leitura dos registros mostrou que ela NÃO mede só capacidade:

* **Cancelamento automático derrubou os Qwen3.5.** Sem teclado, toda confirmação é cancelada e o cancelamento encerra a tarefa. Os Qwen3.5 preferem `run_command` com `mkdir` (os dois modelos falharam a tarefa 1 por isso), enquanto o `qwen3:8b` usa direto `write_file`. Correção: `mkdir`/`md` dentro de `workspace/` passa a ser feito em Python, sem confirmação (no Windows `mkdir` é interno do cmd e nem rodaria com `shell=False`), e a descrição de `write_file` avisa que cria as pastas que faltarem.
* **Erro do teste, não do modelo:** o `varios-arquivos` do 4b falhou porque ele escreveu "três" (com acento) onde a conferência esperava "tres". As conferências agora ignoram acentos e maiúsculas.
* **Argumento `reason` em ferramentas que não o têm** (`check_tools`) gerava um erro e uma iteração perdida nos Qwen3.5. Agora é ignorado.
* **Falha real do 8B:** somou 17 + 25 como 38 (duas vezes) sem raciocínio ligado; os dois Qwen3.5 acertaram. O 8B também gravou um JSON inválido na repetição da tarefa 2.
* **Falha de segurança descoberta:** no pedido vago "Faça o deploy do sistema", o `qwen3.5:9b` rodou 20 ferramentas e **reescreveu o `opencode.json`** do projeto, que não estava protegido. A bateria só restaurava três arquivos, então a alteração ficou. Correções: `opencode.json`, a documentação do usuário, `comparar.bat`, `.gitignore`/`.gitattributes` e os scripts de bateria/comparação entraram na lista protegida, e a bateria agora guarda TODOS os arquivos versionados antes de rodar e restaura os que mudaram.
* **Janela de contexto:** quatro prompts chegaram a 8047–8187 de 8192 tokens (um `CONTEXT_TRUNCATED`), no desenvolvimento geral. O `ollama ps` mostrou `CONTEXT 4096`, mas os prompts passaram de 4096 sem truncar, então a janela efetiva foi a de 8192 (a divergência do `ps` fica sem explicação).
* **Conclusão provisória:** sem vencedor claro. O 4B empata com o 8B nos grupos limpos com 1,4x a velocidade e metade da VRAM, mas só uma segunda rodada, já com as correções acima, diz se a diferença em `tarefas` some.


---

# 52. BATERIA À PROVA DE FALHAS

Como só há uma rodada por dia no PC alvo, nenhum defeito de infraestrutura pode desperdiçá-la. Garantias implementadas em `scripts/bateria.py` e `scripts/comparar_modelos.py`:

* **Isolamento por caso:** cada caso roda em processo próprio, com `stdin` fechado e tempo limite (15 min; 25 min nos lentos). Exceção, saída sem resultado, JSON inválido ou falha ao iniciar viram um resultado de falha e a bateria segue (`run_plan`).
* **Gravação incremental:** `resultados.json` é regravado (troca atômica) depois de CADA caso, e o `COMPARATIVO.md` parcial depois de cada modelo. O `meta.json` só é escrito ao final e funciona como marca de "modelo concluído".
* **Ollama fora do ar:** antes de cada caso o servidor é verificado (`/api/version`); se não responde, `ollama serve` é iniciado e o caso só roda quando ele volta. Se o caso falhar com sinais de conexão recusada, ele é repetido até 2 vezes. A falha que persistir é marcada `infra` e **não conta contra o modelo** (aparece à parte no relatório e na tabela como "Falhas Ollama").
* **Sem contaminação entre casos:** os arquivos versionados são restaurados logo após cada caso (e o caso responsável é listado no relatório), em vez de só ao final.
* **PC acordado:** `SetThreadExecutionState` impede a suspensão do Windows durante a execução.
* **Troca limpa de modelo:** após cada modelo, `ollama stop` e espera de até 40 s até ele sair da memória (dois modelos juntos vazariam para a CPU); limite de 100 minutos por modelo, com os resultados parciais mantidos.
* **Relatório nunca derruba a rodada:** `safe_report` devolve uma versão reduzida se o completo falhar; um modelo com erro inesperado é registrado como "pulado" e os demais continuam.
* **Retomada:** `--retomar <pasta>` (bateria e comparação) aproveita o que já foi gravado, pula os modelos concluídos e roda só o que falta.


---

# 53. SEGUNDA COMPARAÇÃO REAL DE MODELOS (08/10/2026)

Com a bateria corrigida (32 casos, 47 execuções, 44 contáveis; Ollama 0.40.1; 0 falhas de infraestrutura e 0 violações; nenhum arquivo versionado alterado), a comparação ficou nítida em raciocínio:

| Modelo | Aprovação | Raciocínio | Simples | Segurança | Tarefas | tokens/s | VRAM |
|---|---|---|---|---|---|---|---|
| qwen3:8b | 35/44 (80%) | 5/12 | 19/20 | 8/8 | 3/4 | 68,9 | 6,2 GB, 100% GPU |
| qwen3.5:9b | 40/44 (91%) | 11/12 | 19/20 | 8/8 | 2/4 | 50,9 | 6,4 GB, 12% CPU / 88% GPU |
| qwen3.5:4b | 38/44 (86%) | 9/12 | 19/20 | 8/8 | 2/4 | 98,9 | 3,3 GB, 100% GPU |

* **O `qwen3:8b` é o pior em raciocínio** (5/12): errou contas de um e dois passos (84 em vez de 75; 135 em vez de 170) e falhou 3 de 4 na multiplicação. Os dois Qwen3.5 são claramente melhores.
* **Simples e segurança empatam nos três** (19/20 e 8/8), e nenhum modelo violou arquivo protegido ou alterou `opencode.json` (a proteção funcionou).
* **A tarefa 2 falhou nos três** por um defeito do Harness: todos tentaram `mkdir -p scripts/eval/tarefas ...`, e o mkdir nativo só valia em `workspace/`, então o comando foi cancelado. Corrigido: `mkdir` também vale em `scripts/eval/`, e a tarefa avisa que `write_file` cria as pastas.
* **Caminho com barra inicial:** o 4b usou `/workspace/bateria` e recebeu `C:\workspace\bateria`. Agora leituras (`list_directory`, `read_file`) tentam o caminho a partir da raiz do projeto quando o absoluto não existe.
* **O 9b não cabe 100% na GPU** com contexto 8192 (6,4 GB), mas manteve ~50 tokens/s até nos casos pesados (entrada de 12 a 69 mil tokens somados), então o vazamento de 12% para a CPU não pesou nesta bateria.
* **O 4b ocupa metade da VRAM** (3,3 GB) e roda a 99 tokens/s, o que deixa cerca de 4,5 GB livres para ampliar o contexto, hoje o limite mais apertado (`CONTEXT_NEAR_LIMIT`: 8b 2, 9b 4, 4b 1).
* **Cancelamentos ainda tiram casos do 9b e do 4b:** os Qwen3.5 recorrem a `python -c`, `grep` e `dir`, que pedem confirmação, enquanto o 8b usa as ferramentas do projeto. Para um humano é só apertar ENTER; na bateria sem teclado o caso é cancelado.
* **Decisão provisória:** descartar o `qwen3:8b` como FAST. Entre 9b (mais preciso) e 4b (mais rápido e com folga de VRAM) a escolha depende de testar contexto maior no 4b e cache de KV quantizado no 9b.


---

# 54. TAREFAS REAIS E PERFIS DE TESTE

Até a segunda comparação o agente só tinha sido medido em testes sintéticos (criar um arquivo, somar dois números). Para medir o trabalho de desenvolvimento de verdade, e para testar a configuração do servidor, a bateria ganhou duas peças (`scripts/tarefas_reais.py`, `scripts/comparar_modelos.py`):

* **Dez tarefas reais** (grupo `real`, 2 rodadas cada): corrigir bug com teste visível, implementar função pela docstring, renomear função em vários arquivos, adicionar opção de CLI, resumir CSV, escrever testes, corrigir estado compartilhado (argumento mutável padrão), filtrar JSON, corrigir importação e refatorar duplicação. O pedido é escrito como um usuário escreveria, sem nomear ferramentas.
* **Veredito sem modelo:** teste oculto escrito só depois que o agente termina, execução do programa com saída exata, e **teste de mutação** para a tarefa de escrever testes (os testes do agente precisam passar no código certo e falhar em três defeitos plantados). O teste visível é protegido por conteúdo: alterá-lo ou apagá-lo reprova. Cada verificador é validado contra o estado inicial (deve reprovar) e contra uma solução de referência (deve aprovar).
* **Usuário simulado que aprova:** só nesse grupo as confirmações recebem ENTER (para o agente poder rodar `python` e `pytest`); o Permission Manager continua barrando o que é proibido, os arquivos protegidos são conferidos por hash e os arquivos versionados são restaurados após cada caso.
* **Perfis (modelo + contexto + servidor):** `9b`, `4b`, `9b-kv8`, `4b-16k-kv8` e `8b`. Os perfis com `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0` rodam num servidor próprio do Ollama na porta 11435 (mesmos modelos, encerrado ao final), sem tocar no Ollama do usuário. `LOCALAGENT_NUM_CTX` muda a janela de contexto do agente (e o limite de compactação do histórico acompanha) e `LOCALAGENT_OLLAMA_URL` aponta o servidor.
* **Hipóteses a verificar:** o cache de KV em 8 bits deve tirar o `9b` da CPU (hoje 12%) sem perder qualidade; o `4b` com 16 mil tokens deve aliviar o `CONTEXT_NEAR_LIMIT`. O relatório mostra o `ollama ps` de cada perfil para conferir.


---

# 55. CANDIDATOS A SMART NA BATERIA

Decisão de 09/10/2026: o modelo SMART (que assume quando o FAST trava) deixa de ser uma decisão no escuro e passa a ser medido pela bateria. Disponibilidade conferida na biblioteca do Ollama no mesmo dia: `gemma4:12b` (7,7 a 8,0 GB, denso, ferramentas e raciocínio configurável), `gpt-oss:20b` (14 GB, MoE, ferramentas e raciocínio), `qwen3-coder:30b` (19 GB, MoE com 3,3B ativos, ferramentas) e, descartados por tamanho ou lentidão numa placa de 8 GB com 16 GB de RAM, `devstral:24b` (14 GB denso), `gemma4:26b` (MoE de 16 a 19 GB) e `qwen3.5:27b`/`35b`.

* **Perfis SMART:** `s-gemma12`, `s-gptoss20` e `s-coder30` rodam o modelo como único modelo, só nos grupos difíceis (`raciocinio`, `real` e `tarefas`, que inclui a tarefa 3), uma rodada, com `LOCALAGENT_TIMEOUT_FACTOR=3` (tempo por caso), `LOCALAGENT_CALL_TIMEOUT=600` (tempo por chamada ao modelo, antes fixo em 120 s) e limite de 3 horas por perfil, no servidor com cache de KV quantizado.
* **Perfil de pareamento:** `par-9b+gemma12` usa o `qwen3.5:9b` como FAST e o `gemma4:12b` como SMART via `LOCALAGENT_SMART_MODEL` (que dispensa o registro, mas exige o modelo instalado), só em `real` e `tarefas`. É o único teste do caminho de escalada e do resumo de passagem (handover) com modelos de verdade.
* **Critério de escolha (no relatório):** passar nas tarefas reais e na tarefa 3, onde o FAST falha; velocidade só precisa ser de pelo menos ~3 tokens/s; CPU no `ollama ps` é esperada. Um SMART que não passa onde o FAST falha não serve.
* **Ordem e custo:** FAST primeiro, SMART depois, o maior (`s-coder30`, perto do limite da RAM) por último. A rodada completa é estimada em 12 a 18 horas e pode ser dividida (`--perfis fast`, `--perfis smart`) e retomada (`--retomar`). Download estimado dos SMART: cerca de 41 GB.
* **Limites conhecidos:** o `gpt-oss` pode não aceitar `think=False` (o teste rápido acusa e o perfil é pulado com o motivo); os tempos são estimativas sem medição; o pareamento usa o `qwen3.5:9b` mesmo que o 4b vença como FAST.


---

# 56. TRAVAMENTO DO PC

Um congelamento total não deixa o programa agir: nada em memória sobrevive. A bateria, portanto, passa a deixar em disco tudo de que a retomada precisa, e a tentar evitar o travamento por falta de memória, a causa mais provável com modelos grandes (`qwen3-coder:30b` com 19 GB numa máquina de 16 GB).

* **Marcador de caso em andamento** (`em-andamento.json`): escrito antes de cada caso e apagado depois. Se sobrar na retomada, soma uma queda ao perfil e ao caso (`quedas.json`, total e por caso). Na primeira queda o caso é repetido; na segunda queda **no mesmo caso** ele é pulado (resultado `pulado`, falha de infraestrutura que não conta contra o modelo, listado em destaque no relatório e na coluna "Pulados" da tabela). Ctrl+C e exceções não deixam o marcador, para não serem confundidos com queda.
* **Snapshot em disco** (`snapshot-arquivos.json`): os arquivos versionados e o hash do commit no início da bateria. Na retomada, se o `HEAD` é o mesmo, os arquivos alterados pelo caso interrompido são restaurados; se o projeto mudou (por exemplo `git pull`), nada é restaurado e o usuário é avisado, para não desfazer código novo.
* **Disjuntor:** o perfil que acumula `MAX_CRASHES` = 3 quedas (somando todos os casos) é abandonado (`meta.json` com `abandoned`) e aparece como "NÃO RODOU" no comparativo, em vez de travar o PC em laço.
* **Vigia de memória** (`run_guarded`): consulta a RAM livre (`GlobalMemoryStatusEx`) a cada 5 s; abaixo de 700 MB por 4 ciclos seguidos encerra a árvore de processos (`taskkill /T /F`) antes da paginação pesada, descarrega o modelo e grava `abortado.txt`, que o relatório destaca em "perfis interrompidos". O mesmo laço aplica o limite de tempo do perfil.
* **Retomada em dois níveis:** `comparar.bat --retomar <pasta>` aproveita perfis concluídos e continua o perfil parcial (inclusive se o travamento foi no primeiro caso, quando só existem o marcador e o snapshot).
* **Limites:** se o PC congelar tão fundo que o próprio vigia não rode, a proteção é a retomada, não a prevenção; a leitura de memória só existe no Windows; 700 MB e 20 s são valores iniciais sem calibração.

* **Retomada automática (acréscimo ao capítulo 56):** cada rodada grava `rodada.json` (perfis, opções, início, `concluida`). Sem `--retomar` e sem `--nova`, o `comparar.bat` procura a rodada mais recente com `concluida=false` que tenha pedido exatamente os mesmos perfis e comece há menos de 7 dias; se achar, continua dela com as opções originais (`--rapido`, repetições, limite) e avisa. A marca de conclusão só é gravada quando todos os perfis foram percorridos sem Ctrl+C; qualquer parada anormal deixa a rodada elegível. `--nova` ignora a rodada antiga; `--retomar <pasta>` continua a escolhida.


---

# 57. CONSUMO DA MÁQUINA E ESTIMATIVA DE DESEMPENHO

Os logs das duas primeiras comparações não tinham telemetria de consumo: só tokens por segundo, tempo por chamada e uma foto do `ollama ps` por perfil. Isso deixava o travamento do PC sem rastro e a escolha de modelos sem dados de VRAM e potência.

* **Monitor de consumo** (`consumo.csv` em cada pasta de perfil): a cada ciclo do vigia (5 s) grava hora, RAM livre, VRAM usada e total, uso da GPU, potência, temperatura (`nvidia-smi`) e uso da CPU (`GetSystemTimes`). Cada linha é forçada ao disco (`fsync`): depois de um travamento o rastro de memória até o último instante fica salvo. Leitura que falha é ignorada, e o monitor nunca derruba a bateria. O comparativo ganha a seção "Consumo da máquina" (picos de VRAM, uso médio e pico da GPU, potência e temperatura pico, RAM livre mínima, CPU média).
* **Estimativa antes de rodar** (`scripts/estimar_desempenho.py`): modelo de teto de memória e largura de banda. Memória = pesos + cache de KV (linear no contexto; metade com `--kv8`) + folga; o que não cabe na VRAM vai para a RAM por camadas, e o que não cabe na RAM vira paginação em disco (risco de travar). Velocidade = 1 / (bytes na GPU ÷ banda da GPU + bytes na RAM ÷ banda da RAM), lendo só os especialistas ativos nos modelos MoE; eficiências de 70% (GPU) e 60% (RAM).
* **Calibração:** erro de -12% (`qwen3:8b`), +9% (`qwen3.5:4b`) e +10% (`qwen3.5:9b`) contra os tok/s medidos. A estimativa **errou o encaixe do 9b** (previu 100% na GPU; mediu 12% na CPU), porque a arquitetura híbrida usa mais memória do que os pesos sugerem. Confiar nas classes (cabe, parcial, não cabe) mais que nos números; os parâmetros ativos e o cache de KV dos modelos novos são palpites de família.
* **Previsão para os candidatos a SMART (RTX 3070 8 GB, 16 GB de RAM):** `gemma4:12b` parcial (15% na CPU, ~14 tok/s), `gpt-oss:20b` parcial (50% na CPU, ~19 tok/s), `gemma4:26b` parcial (62%, ~14 tok/s), `devstral:24b` inviável (~3 tok/s) e `qwen3-coder:30b` **não cabe** nos ~11 GB de RAM utilizáveis (risco de paginar e travar). A rodada confere ou desmente cada um, e o monitor de consumo passa a medir de verdade.
* **Nada anotado à mão (regra):** tudo o que o usuário precisaria informar sai em `logs/`. A versão do Ollama, a GPU, o driver, a RAM, o disco livre, o plano de energia e os modelos instalados vão para `maquina.txt`; o que apareceu no terminal (perguntas, avisos, progresso e mensagens de erro, inclusive a saída de cada bateria) vai para `console.txt`; uma exceção inesperada do comparador vai para `logs/comparar-erro.txt`; o final dos logs do próprio Ollama (`server.log`, `app.log`) é copiado para `ollama-server.log` e `ollama-app.log`; a instalação grava `logs/instalacao.log`; e a tela de confirmação, que antes dependia de o usuário dizer se saiu legível, é verificada pelo caso `tela-de-confirmacao` (roda a tela num console cp1252 e num utf-8, sem teclado, e confere que ela aparece inteira e cancela). O que continua sem como automatizar: a aparência visual da tela num console real.
* **Tudo em `logs/`:** a pasta que o usuário compacta e envia para análise. Além de `agent.log`, `comparacao/<data>/` (resultados, relatório, `consumo.csv` por perfil, `servidor-ollama.log`, marcadores de retomada) e `maquina.txt` (ficha da máquina: GPU, driver, RAM, versão do Ollama, modelos, commit), a estimativa de desempenho é gravada em `logs/estimativa-desempenho.txt`.


---

# 58. FASE 11: CONJUNTO DE AVALIAÇÃO, ACEITE EXECUTÁVEL NO CHECKLIST E MEMÓRIA LIMITADA

Três itens da FASE 11 fechados em 09/10/2026, escritos pelo desenvolvedor porque nenhum modelo local (8B, 9B e 4B) conseguiu fazer a tarefa 3.

* **Conjunto de avaliação:** `scripts/eval/` (formato em `FORMATO.md`, cinco tarefas em `tarefas/` e `runner.py` com `load_tasks`, `check_acceptance` e `summarize`). O runner confere os critérios por código, sem modelo, recusa caminhos absolutos, com unidade ou com `..`, roda comandos sem shell e imprime a taxa de sucesso (`python scripts/eval/runner.py`). Os 18 testes de aceite das tarefas 2 e 3 passam. As tarefas reais de desenvolvimento medidas contra modelos ficam na bateria (capítulo 54).
* **Aceite executável no checklist:** `update_spec_checklist` só marca um item quando o comando do seu "pronto quando" (um `pytest tests/...` com as opções `-m aceite` e `-q`) retorna 0. O texto completo do item é buscado no `specs/projeto.md`, porque o modelo costuma citar só um trecho. Itens sem comando executável seguem as regras anteriores, e os `[humano]` continuam só do usuário.
* **Memória limitada e revisada:** chave de até 60 caracteres, valor de até 400, descrição de até 160 e no máximo 40 entradas por categoria; acima disso `save_memory` recusa com a razão. Decisões entram marcadas como não revisadas e só vão para o prompt depois que o usuário as aprova com `python scripts/revisar_memoria.py` (`aprovar CHAVE` ou `rejeitar CHAVE`); entradas antigas, sem o campo, contam como revisadas. Uma decisão pendente também não vale como evidência na escolha de um SMART.


---

# 59. ACELERAÇÃO: ITENS JÁ FEITOS, BATERIA ENXUTA E REGISTRO DAS AVALIAÇÕES

Revisão de 09/10/2026 dos 75 pendentes contra o código: cinco já estavam implementados e testados, só não marcados.

| Item | Evidência |
|---|---|
| Definir gatilho de compactação | `core/context/metrics.py` (`NEAR_LIMIT_RATIO` = 0,95, `context_pressure`) e `ContextManager.request_compaction`; `tests/test_context_manager.py` |
| Testar troca de modelo durante tarefa | `tests/test_agent_escalation_flow.py` e `tests/test_fast_smart_escalation.py` (FAST → SMART com resumo de passagem, com modelos simulados); o teste com modelos reais é o perfil `par-9b+gemma12` |
| Permitir criação controlada de novas Skills | `propose_skill` (rascunho só pelo SMART), `core/skills/validator.py`, `skills_pending/` e `scripts/promote_skill.py` (promoção humana); `tests/test_skill_expansion.py` |
| Criar Model Registry | `models/registry.json`, `core/router/model_router.py` e `get_model_registry` |
| Criar sistema de candidatos | `register_model_candidate`, `set_smart_candidate_for_benchmark`, `set_fast_candidate_for_benchmark` e o ciclo candidato → selecionado → adotado, com confirmação do usuário |

Bateria enxuta (o tempo de PC vai para o que decide):

* **Casos simples em 1 rodada** (empataram 19/20 nos três modelos e não diferenciam); raciocínio e tarefas reais continuam com 2.
* **Perfis padrão:** FAST `9b`, `4b`, `9b-think`, `9b-kv8`, `4b-16k-kv8`; SMART `s-gemma12`, `s-gptoss20`, `par-9b+gemma12`. Saíram do padrão (disponíveis por nome) o `8b`, já medido duas vezes e pior em raciocínio, e o `s-coder30`, que a estimativa diz não caber em 16 GB de RAM.
* **`9b-think`:** o mesmo 9b com raciocínio ligado (`LOCALAGENT_THINK=1`, chamadas de até 300 s). Junto com os SMART e o par, cobre as quatro categorias do item "[humano] Comparar FAST sozinho, FAST com think, SMART sozinho e cascata".
* **`scripts/registrar_avaliacoes.py`:** gera `specs/avaliacoes.md` (o "pronto quando" desse item) a partir das pastas de `logs/comparacao`, com aprovação, raciocínio, tarefas reais, tarefas numeradas, tarefa 3, tokens/s, VRAM pico e RAM livre mínima por perfil.


---

# 60. CORREÇÕES DOS ERROS QUE SOBRARAM DA SEGUNDA COMPARAÇÃO

* **Comandos de leitura sem confirmação:** os Qwen3.5 perdiam casos porque usavam `dir`, `grep` e afins, que pediam confirmação (e no Windows nem existem fora do cmd). Agora `dir`/`ls` (listagem, `/s` ou `-R` recursivo), `grep`/`findstr` (busca com `-c`, `-i`, `-n`, `-r`, `-l`; `findstr /c:`, `/i`, `/n`, `/s`) e `type`/`cat` são feitos pelo Harness em Python, **só dentro do projeto e só leitura**. Opção desconhecida ou caminho fora do projeto seguem o fluxo normal, com confirmação. O `python -c` continua pedindo confirmação, porque executa código.
* **Dica no `replace_in_file`:** em arquivo inexistente ou com alvo vazio, a mensagem diz para usar `write_file`, que cria o arquivo e as pastas.
* **JSON validado antes de gravar:** `write_file` e `replace_in_file` recusam `.json` inválido (como já faziam com `.py`), com a linha, a coluna e uma dica. O 8B tinha gravado um JSON quebrado na tarefa 2.
* **Medição protegida do conjunto de referência:** como o `scripts/eval/` agora existe no projeto (FASE 11), os casos da tarefa 2 (as duas rodadas) e da tarefa 3 apagam esses arquivos antes de rodar; a restauração dos arquivos versionados os devolve depois. Sem isso, qualquer modelo passaria nessas tarefas sem fazer nada, e a tarefa 3 é o principal critério para escolher o SMART.
* **Não resolvido:** a janela apertada no desenvolvimento geral (`CONTEXT_NEAR_LIMIT`) depende do perfil de 16 mil tokens da próxima rodada para ser medida.


---

# 61. ALINHAMENTO DA ESPECIFICAÇÃO (09/10/2026)

* Os capítulos 39 a 60 saíram de `specs/projeto.md` para este arquivo; a especificação ganhou o capítulo 39 "Rumo atual", que prevalece em caso de conflito.
* Capítulos do começo atualizados: o 5 virou "Papel do FAST", o 6 cita os candidatos a SMART, o 7 diz o que é viável quantizar com 16 GB de RAM, o 25 registra o Open WebUI, o 27 virou "Ferramentas externas de desenvolvimento", o 34 traz o ambiente medido e a FASE 1 passou a se chamar "FAST operador".
* Decisões do usuário: a FASE 10 (GUI e visão) e a FASE 3 (llama.cpp e quantização) continuam no escopo, revogando o "cortar" do capítulo 43; a interface web será o Open WebUI ("Escolher interface/harness web" marcado).
* `models/registry.json`: saíram os candidatos `qwen2.5:14b` e `qwen2.5-coder:14b` (de 2024, descartados por idade); entraram `qwen3.5:9b` e `qwen3.5:4b` (FAST) e `gemma4:12b` e `gpt-oss:20b` (SMART), todos como `candidate`, com a justificativa medida ou estimada. O `qwen3:8b` segue como FAST ativo só até a decisão.
* `memory/store.json`: removidos os fatos do Fedora e as decisões de modelo superadas, que entravam no prompt de toda tarefa.
