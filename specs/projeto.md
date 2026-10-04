# PROJETO — AGENTE LOCAL AUTÔNOMO

> Especificação central do projeto.
>
> Este documento descreve a arquitetura, objetivos, etapas, estado atual e regras do agente local.
>
> O documento deve ser atualizado conforme o projeto evoluir.

---

# 1. OBJETIVO

Construir um agente de IA **100% local e gratuito**, capaz de executar tarefas reais no computador de forma autônoma.

O objetivo não é criar apenas um chatbot.

O agente deve ser capaz de:

* ler e modificar arquivos;
* executar comandos;
* instalar ferramentas e dependências;
* pesquisar na internet;
* consultar GitHub;
* baixar arquivos;
* ler documentação;
* analisar README e changelogs;
* trabalhar com Git;
* criar scripts;
* diagnosticar erros;
* instalar e atualizar mods;
* trabalhar com jogos;
* trabalhar com modelos de IA;
* quantizar modelos;
* testar modelos;
* comparar modelos;
* criar e modificar suas próprias ferramentas e Skills dentro das permissões permitidas;
* executar tarefas completas e retornar um resumo do resultado.

Exemplo de tarefa desejada:

> "Verifique se saiu atualização daquele mod do STALKER 2 e instale."

O agente deve ser capaz de:

1. pesquisar na internet;
2. localizar a fonte oficial;
3. identificar a versão atual;
4. verificar a versão instalada;
5. consultar README/documentação/changelog;
6. verificar compatibilidade;
7. baixar a atualização;
8. localizar a instalação do jogo;
9. fazer backup;
10. instalar;
11. validar;
12. informar o resultado.

---

# 2. PRINCÍPIOS

## 2.1 Local primeiro

O objetivo final é que o sistema funcione sem depender de APIs pagas ou serviços externos de IA.

Internet pode ser utilizada para:

* pesquisa;
* GitHub;
* documentação;
* downloads;
* atualização de software;
* descoberta de modelos.

A IA principal deve ser local.

Serviços externos podem ser utilizados durante desenvolvimento, benchmarking ou bootstrap, mas não devem ser tratados como dependência da arquitetura final.

---

## 2.2 O modelo não é o sistema

O LLM é apenas uma parte do projeto.

A arquitetura deve ser independente do modelo.

O sistema deve permitir trocar:

* modelo;
* quantização;
* backend;
* quantidade de modelos;
* contexto.

Sem precisar reconstruir o agente.

---

## 2.3 O Harness é o orquestrador

O Harness será responsável por:

* escolher modelos;
* disponibilizar ferramentas;
* controlar permissões;
* controlar contexto;
* controlar memória;
* controlar tarefas;
* controlar Skills;
* monitorar execução;
* detectar erros;
* decidir quando escalar para outro modelo;
* registrar resultados.

O LLM raciocina.

O Harness controla.

---

## 2.4 Soluções existentes devem ser avaliadas antes de serem recriadas

O projeto não deve implementar manualmente uma funcionalidade que já exista de forma madura sem antes avaliar a possibilidade de reutilização.

Isso inclui:

* Harnesses;
* runtimes;
* gerenciadores de modelos;
* sistemas de Skills;
* ferramentas de execução;
* mecanismos de contexto;
* interfaces;
* ferramentas de benchmark.

Porém, uma ferramenta externa não deve ser adotada automaticamente.

A decisão deve considerar:

* compatibilidade com arquitetura;
* controle;
* segurança;
* execução local;
* possibilidade de substituição;
* desempenho;
* manutenção;
* dependências externas.

---

# 3. HARDWARE

Hardware inicial:

* CPU: Ryzen 5 5600G
* GPU: NVIDIA RTX 3070 8 GB
* Sistema: Fedora KDE
* RAM: utilizar toda a RAM disponível para permitir CPU offload quando necessário.

O projeto deve considerar que:

* modelos maiores podem não caber inteiramente na VRAM;
* parte do modelo pode utilizar RAM/CPU;
* isso pode reduzir bastante a velocidade;
* o tamanho em parâmetros não determina sozinho se o modelo é utilizável.

Não estabelecer um limite artificial de tamanho de modelo.

O sistema deverá descobrir empiricamente o que é viável.

---

# 4. FILOSOFIA DE MODELOS

A arquitetura deverá trabalhar com múltiplos modelos.

Inicialmente:

```text
FAST / OPERATOR
≈ 8B

SMART / SPECIALIST
(tamanho determinado por benchmark)
```

Futuramente:

```text
FAST
SMART
HEAVY
```

O terceiro modelo pode ser algo como:

* 20B;
* 24B;
* 30B;
* outro tamanho.

O tamanho não deve ser fixo.

O limite deve ser determinado por benchmark.

---

# 5. PAPEL DO 8B

O 8B será o primeiro modelo instalado.

Seu objetivo inicial é funcionar como operador/bootstrapper.

Ele deverá ser capaz de:

* conversar;
* executar comandos;
* ler arquivos;
* criar arquivos;
* instalar ferramentas;
* pesquisar documentação;
* preparar o ambiente;
* baixar modelos;
* preparar ferramentas de quantização;
* quantizar/testar modelos;
* instalar o próximo modelo;
* registrar resultados.

O 8B não precisa construir todo o Harness inicialmente.

Ele deve primeiro conseguir executar tarefas reais.

---

# 6. PAPEL DO SMART

O modelo SMART será o primeiro modelo especialista.

O papel SMART não é definido pelo tamanho do modelo — é determinado pela capacidade
de raciocínio avançado e aprovação em benchmark comparativo com outros candidatos.

Depois de instalado, deverá assumir tarefas que exigem mais raciocínio.

Exemplos:

* programação;
* debugging;
* planejamento;
* análise de documentação;
* criação e evolução do Harness;
* criação do Context Manager;
* criação do Model Router;
* criação de Skills;
* criação da interface;
* análise de benchmarks;
* otimização do sistema.

O modelo SMART pode também revisar a quantização feita inicialmente pelo FAST.

---

# 7. QUANTIZAÇÃO

O FAST poderá preparar e executar a primeira quantização de um modelo maior.

Depois que o modelo SMART estiver funcionando, ele poderá:

1. auditar a configuração;
2. verificar as quantizações disponíveis;
3. testar alternativas;
4. comparar qualidade;
5. comparar velocidade;
6. comparar VRAM;
7. comparar RAM;
8. verificar contexto;
9. selecionar uma configuração melhor.

O modelo SMART não necessariamente "quantiza melhor".

A ferramenta de quantização realiza o processo.

O ganho do modelo SMART está em conseguir:

* escolher melhor os parâmetros;
* experimentar alternativas;
* analisar resultados;
* decidir qual configuração é mais adequada.

---

# 8. MODELOS NÃO DEVEM SER DEFINIDOS PERMANENTEMENTE

O sistema deve permitir descobrir novos modelos.

Um modelo novo poderá ser:

* mais rápido;
* mais inteligente;
* mais eficiente;
* mais econômico em VRAM;
* melhor em tool calling;
* melhor em programação;
* melhor em contexto;
* melhor para determinado tipo de tarefa.

Portanto:

> O modelo atualmente instalado nunca deve ser tratado como definitivamente ideal.

---

# 9. MODEL SCOUT

Futuramente o agente deverá possuir uma capacidade chamada **Model Scout**.

Objetivo:

Pesquisar periodicamente modelos novos disponíveis publicamente.

Fontes possíveis:

* Hugging Face;
* GitHub;
* documentação oficial;
* releases;
* benchmarks públicos.

O agente deverá considerar:

* número de parâmetros;
* arquitetura;
* quantizações disponíveis;
* tamanho do arquivo;
* requisitos de RAM;
* requisitos de VRAM;
* contexto;
* tool calling;
* qualidade esperada;
* compatibilidade com nosso hardware.

---

# 10. DESCOBERTA ≠ ADOÇÃO

Encontrar um modelo não significa instalá-lo como padrão.

Fluxo:

```text
DESCOBERTA
    ↓
FILTRAGEM
    ↓
DOWNLOAD
    ↓
BENCHMARK
    ↓
COMPARAÇÃO
    ↓
STAGING
    ↓
TESTE
    ↓
APROVAÇÃO
    ↓
MODELO ATIVO
```

O agente não deve substituir automaticamente um modelo apenas porque ele parece melhor.

Primeiro deve comparar com o modelo atual.

---

# 11. BENCHMARK DE MODELOS

Devem existir pelo menos dois perfis de benchmark.

## 11.1 Benchmark FAST / 8B

Objetivo:

Encontrar o melhor modelo pequeno para operação.

Métricas:

* tokens/s;
* latência;
* VRAM;
* RAM;
* estabilidade;
* tool calling;
* execução de comandos;
* seguimento de instruções;
* código simples;
* resistência a loops.

---

## 11.2 Benchmark SMART

Objetivo:

Encontrar o melhor modelo especialista disponível para o hardware.

Métricas:

* raciocínio;
* programação;
* debugging;
* planejamento;
* documentação;
* tool calling complexo;
* correção de erros;
* tokens/s;
* VRAM;
* RAM;
* estabilidade;
* contexto.

---

# 12. TESTES REAIS

Benchmarks não devem depender somente de números sintéticos.

Devem existir tarefas reais.

Exemplos:

```text
TESTE 1
Criar um script Python.

TESTE 2
Ler um README e identificar requisitos.

TESTE 3
Encontrar uma release no GitHub.

TESTE 4
Executar um comando e corrigir um erro.

TESTE 5
Preparar uma quantização.

TESTE 6
Usar múltiplas ferramentas para completar uma tarefa.

TESTE 7
Analisar documentação e produzir um plano.

TESTE 8
Executar uma tarefa longa sem entrar em loop.
```

---

# 13. BENCHMARK DE CONTEXTO

O benchmark completo de contexto não será prioridade no 8B inicial.

A prioridade inicial é:

```text
8B funcionando
+
ferramentas básicas
```

Depois que o modelo SMART estiver funcionando, executar o benchmark de contexto.

Testar progressivamente:

```text
8K
16K
24K
32K
40K
48K
64K
...
```

Medir:

* VRAM;
* RAM;
* tokens/s;
* estabilidade;
* OOM;
* latência;
* qualidade;
* capacidade de executar tarefas.

O objetivo é encontrar:

```text
MAX_CONTEXT
SAFE_CONTEXT
```

---

# 14. CONTEXT MANAGER

O sistema não deve enviar todo o histórico ao modelo continuamente.

O Context Manager deverá organizar:

```text
CONTEXTO ATIVO
├── objetivo
├── estado atual
├── últimas ações
├── erros recentes
├── arquivos relevantes
├── documentação relevante
├── memória relevante
└── resumo anterior
```

Informações irrelevantes devem ficar fora do contexto ativo.

---

# 15. COMPACTAÇÃO

Quando o contexto atingir aproximadamente 50% do limite operacional definido pelo benchmark:

```text
contexto cresce
      ↓
~40%
      ↓
preparar compactação
      ↓
~50%
      ↓
compactar
      ↓
resumo estruturado
      ↓
contexto reduzido
      ↓
continuar tarefa
```

A compactação deverá preservar:

* objetivo;
* decisões;
* arquivos importantes;
* comandos executados;
* resultados;
* erros;
* versões;
* estado atual;
* próxima ação.

Não simplesmente resumir a conversa inteira.

---

# 16. TASK STATE

Cada tarefa deverá possuir estado persistente.

Exemplo:

```json
{
  "goal": "Atualizar mod do STALKER 2",
  "status": "installing",
  "current_version": "x.x",
  "target_version": "x.y",
  "game_path": "/games/STALKER 2",
  "backup": true,
  "actions_completed": [
    "searched_github",
    "checked_release",
    "downloaded_mod",
    "created_backup"
  ],
  "next_action": "install_files"
}
```

O estado deverá sobreviver a:

* troca de modelo;
* compactação;
* reinício;
* interrupção da tarefa.

Uma implementação inicial de `TaskState` já existe no projeto.

---

# 17. MODEL ROUTER

O Harness deverá decidir qual modelo utilizar.

Exemplo:

```text
TAREFA
  ↓
análise
  ↓
FAST
  ↓
tarefa simples?
 ├── SIM → continua
 └── NÃO
       ↓
     SMART
```

Se necessário:

```text
SMART
  ↓
tarefa extremamente complexa
  ↓
HEAVY
```

O terceiro modelo só existirá se o benchmark demonstrar que vale a pena.

---

# 18. ESCALADA

O Harness deve poder escalar automaticamente.

Possíveis gatilhos:

* muitos tokens;
* muitas chamadas de ferramentas;
* erros consecutivos;
* repetição;
* falta de progresso;
* tempo excessivo;
* tarefa classificada como complexa;
* modelo solicitar ajuda;
* falha de execução.

A decisão final de escalada deve pertencer ao Harness, não somente ao modelo.

---

# 19. FERRAMENTAS

Começar com poucas ferramentas.

## Fase inicial

```text
read_file
write_file
list_directory
run_command
```

Essas ferramentas já possuem implementação funcional inicial.

## Depois

```text
web_search
download_file
git
python
inspect_file
extract_archive
process_manager
```

## Futuramente

```text
browser
screenshot
mouse
keyboard
GUI automation
```

Não implementar ferramentas desnecessárias no início.

---

# 20. SKILLS

Skills descrevem como executar determinados tipos de tarefas.

Estrutura:

```text
skills/
├── linux/
│   └── SKILL.md
├── github/
│   └── SKILL.md
├── mods/
│   └── SKILL.md
├── games/
│   └── SKILL.md
└── models/
    └── SKILL.md
```

Exemplo de Skill de mods:

```text
1. procurar fonte oficial;
2. identificar versão;
3. verificar compatibilidade;
4. ler README;
5. consultar changelog;
6. localizar instalação;
7. fazer backup;
8. instalar;
9. validar;
10. informar resultado.
```

Skills devem ser tratadas como procedimentos operacionais.

O projeto já possui um mecanismo inicial de carregamento de Skills e uma Skill de gerenciamento de ambiente.

---

# 21. AUTOEXPANSÃO

O agente poderá criar ou modificar:

* ferramentas;
* Skills;
* scripts;
* testes;
* documentação.

Porém:

> O agente não pode conceder novas permissões ao próprio sistema.

Por exemplo, não pode automaticamente conceder:

```text
sudo ilimitado
```

ou:

```text
acesso irrestrito a arquivos do sistema
```

O Harness deve controlar as permissões.

---

# 22. PERMISSÕES

## Permitido automaticamente

* leitura de arquivos;
* escrita dentro do workspace;
* criação de scripts;
* execução de comandos seguros;
* Git;
* internet;
* downloads;
* análise de arquivos.

## Solicitar confirmação

* sudo;
* instalação de pacotes do sistema;
* alteração de `/etc`;
* exclusão de arquivos importantes;
* substituição de arquivos;
* execução de binários desconhecidos;
* operações potencialmente destrutivas.

## Bloqueado por padrão

Operações destrutivas ou perigosas fora do escopo do agente.

O Permission Manager já possui uma implementação inicial.

A proteção também é aplicada na execução do terminal, e não deve depender exclusivamente da decisão do modelo.

---

# 23. MEMÓRIA

O sistema deverá possuir memória externa ao contexto do modelo.

Possíveis componentes:

```text
memory/
├── project/
├── models/
├── tools/
├── tasks/
└── history/
```

A memória poderá guardar:

* modelos testados;
* resultados de benchmark;
* ferramentas disponíveis;
* Skills;
* configurações;
* tarefas anteriores;
* decisões importantes.

---

# 24. MODEL REGISTRY

Deverá existir um registro dos modelos conhecidos.

Exemplo:

```json
{
  "name": "nome-do-modelo",
  "version": "x.x",
  "quantization": "Q5_K_M",
  "context": 32768,
  "vram": "x GB",
  "tokens_per_second": "x",
  "status": "active",
  "benchmark_date": "YYYY-MM-DD"
}
```

O registro evita:

* baixar novamente o mesmo modelo;
* repetir benchmarks desnecessários;
* perder resultados;
* esquecer qual modelo está ativo.

---

# 25. INTERFACE WEB

A interface deverá ser adicionada depois que o agente básico estiver funcional.

Arquitetura:

```text
Browser
   ↓
Web UI
   ↓
Harness
   ├── Models
   ├── Tools
   ├── Skills
   ├── Context
   ├── Memory
   └── Permissions
```

A interface deverá mostrar:

* conversa;
* tarefa atual;
* ações;
* ferramentas utilizadas;
* logs;
* status;
* pedidos de autorização;
* resultado final.

Exemplo:

```text
🔎 Pesquisando
📖 Lendo README
⬇ Baixando
📁 Localizando instalação
💾 Criando backup
⚙ Instalando
✓ Validando
✓ Concluído
```

---

# 26. ESTRUTURA DO PROJETO

Estrutura inicial desejada:

```text
local-agent/
│
├── core/
│   ├── harness/
│   ├── context/
│   ├── router/
│   ├── memory/
│   └── permissions/
│
├── models/
│   ├── registry.json
│   └── configs/
│
├── tools/
│   ├── filesystem/
│   ├── terminal/
│   ├── web/
│   └── git/
│
├── skills/
│   ├── linux/
│   ├── github/
│   ├── mods/
│   ├── games/
│   └── models/
│
├── tasks/
│
├── workspace/
│
├── logs/
│
├── benchmarks/
│
├── specs/
│
└── config/
```

A estrutura real pode evoluir conforme o desenvolvimento.

A especificação não deve obrigar a criação de diretórios ou componentes que não sejam necessários.

---

# 27. PAPEL DO ANTIGRAVITY

O Antigravity é uma ferramenta externa de desenvolvimento e bootstrap.

A visão original era utilizá-lo apenas para:

* preparar ambiente;
* instalar backend;
* baixar modelo 8B;
* configurar modelo;
* deixar o 8B funcionando;
* testar execução básica.

Entretanto, durante o desenvolvimento, o Antigravity também pode ser utilizado para:

* analisar o projeto;
* avaliar decisões arquiteturais;
* pesquisar alternativas;
* implementar ou corrigir componentes;
* acelerar desenvolvimento;
* testar abordagens.

Isso **não significa que o Antigravity faça parte da arquitetura final do agente**.

O sistema final deve continuar sendo capaz de funcionar localmente sem depender do Antigravity.

---

# 28. BOOTSTRAP

Fluxo inicial:

```text
ANTIGRAVITY
     ↓
ambiente
     ↓
backend local
     ↓
modelo 8B
     ↓
teste
     ↓
8B funcionando
```

A partir daqui, o objetivo arquitetural continua sendo:

```text
8B
 ↓
prepara ferramentas
 ↓
baixa modelo maior
 ↓
quantiza
 ↓
testa
 ↓
instala modelo SMART
```

Depois:

```text
SMART
 ↓
evolui Harness
 ↓
Context Manager
 ↓
Model Router
 ↓
Tools
 ↓
Skills
 ↓
Memory
 ↓
Web UI
```

A ordem acima é uma direção arquitetural, não uma obrigação rígida.

O agente deve avaliar o estado real do projeto e determinar qual componente é necessário em cada momento.

---

# 29. FILOSOFIA DE DESENVOLVIMENTO

Não construir tudo de uma vez.

A pergunta principal durante o desenvolvimento deve ser:

> **"O que falta para o agente conseguir executar essa tarefa sozinho?"**

Se falta conhecimento:

```text
→ Skill
```

Se falta capacidade:

```text
→ Tool
```

Se falta raciocínio:

```text
→ modelo melhor
```

Se falta memória:

```text
→ Memory
```

Se falta espaço de contexto:

```text
→ Context Manager / compactação
```

Se está errando:

```text
→ escalada para modelo maior
```

Se precisa de autorização:

```text
→ Permission Manager
```

Não implementar componentes apenas porque aparecem no checklist.

O checklist representa objetivos do projeto, não necessariamente a melhor ordem de implementação.

---

# 30. CHECKLIST GERAL

## FASE 0 — BOOTSTRAP

* [x] Preparar ambiente Fedora
* [x] Escolher backend local
* [x] Instalar backend
* [x] Baixar modelo 8B
* [x] Fazer modelo responder
* [x] Testar execução básica
* [x] Testar uso de GPU
* [x] Registrar configuração

---

## FASE 1 — 8B OPERADOR

* [x] Implementar `read_file`
* [x] Implementar `write_file`
* [x] Implementar `list_directory`
* [x] Implementar `run_command`
* [x] Fazer 8B usar ferramentas
* [x] Testar tarefas simples
* [x] Registrar logs
* [x] Testar tarefas multi-etapas
* [x] Testar decisões condicionais
* [x] Testar recuperação após falha de ferramenta
* [x] Testar validação do resultado
* [x] Implementar Task State mínimo
* [x] Validar tratamento de conclusão de tarefa
* [x] Revisar e endurecer Permission Manager
* [x] Criar testes automatizados do Harness
* [x] Testar execução real de `run_command`
* [x] Testar rejeição de comandos compostos
* [x] Testar cancelamento de ações que exigem confirmação
* [x] Implementar restrições específicas da tarefa
* [x] Garantir bloqueio efetivo de instalações quando proibidas
* [x] Garantir bloqueio de alterações do sistema quando proibidas
* [x] Garantir bloqueio de operações destrutivas quando proibidas
* [x] Criar carregamento inicial de Skills
* [x] Criar Skill de gerenciamento de ambiente
* [x] Fazer 8B instalar ferramentas adicionais
* [x] Fazer 8B preparar ambiente para modelo maior

---

## FASE 2 — SMART — Seleção do Modelo Especialista

> **Contrato desta fase:**
> - "Escolher modelo SMART candidato" significa: pelo menos 2 candidatos registrados no Model Registry
>   com justificativa técnica, dados de hardware (vram_gb, size_gb) e um candidato com status
>   `selected_for_benchmark`. SMART é um papel arquitetural — o tamanho do modelo não define o papel.
> - "Baixar modelo" NÃO é autorização automática para executar `ollama pull`. Exige:
>   (1) candidato com status `selected_for_benchmark` no registry;
>   (2) autorização/confirmação explícita do usuário antes do download.
> - `selected_for_benchmark` é distinto de `adopted`. O modelo só é adotado após benchmark
>   e chamada explícita a `set_active_smart_model()`.
> - Se nenhum candidato for adequado ao hardware, `NO_SUITABLE_CANDIDATE` é uma decisão válida.

* [x] Escolher modelo SMART candidato
* [ ] Baixar modelo
* [ ] Preparar quantização
* [ ] Gerar quantização inicial
* [ ] Testar modelo
* [ ] Comparar configurações
* [ ] Instalar versão escolhida
* [ ] Registrar resultado

---

## FASE 3 — BENCHMARK + RUNTIME DO SMART

* [ ] Executar benchmark inicial do modelo SMART no Ollama
* [ ] Configurar llama.cpp
* [ ] Executar benchmark do mesmo modelo SMART no llama.cpp
* [ ] Comparar VRAM
* [ ] Comparar RAM
* [ ] Comparar velocidade
* [ ] Comparar latência
* [ ] Comparar estabilidade
* [ ] Comparar tool calling
* [ ] Comparar execução de código
* [ ] Comparar raciocínio
* [ ] Comparar contexto
* [ ] Determinar `MAX_CONTEXT`
* [ ] Determinar `SAFE_CONTEXT`
* [ ] Definir gatilho de compactação
* [ ] Comparar resultados Ollama vs llama.cpp
* [ ] Escolher runtime principal
* [ ] Definir interface abstrata do Model Backend
* [ ] Registrar configuração e resultados finais

---

## FASE 4 — HARNESS

* [x] Criar Harness inicial
* [x] Criar gerenciamento inicial de ferramentas
* [x] Criar sistema inicial de permissões
* [x] Criar Task State inicial
* [x] Criar logs
* [x] Criar tratamento de erros
* [x] Criar tratamento de conclusão
* [x] Criar gerenciamento de modelos
* [x] Criar Model Router
* [x] Criar escalada automática
* [x] Evoluir Harness conforme necessidades reais das tarefas

---

## FASE 5 — CONTEXTO E MEMÓRIA

* [x] Criar Context Manager
* [x] Implementar contexto ativo
* [x] Integrar Task State ao gerenciamento de contexto
* [x] Implementar memória persistente
* [x] Implementar compactação
* [x] Implementar recuperação de contexto
* [ ] Testar tarefas longas
* [ ] Testar troca de modelo durante tarefa

---

## FASE 6 — SKILLS

* [x] Criar sistema inicial de Skills
* [x] Criar mecanismo de carregamento de Skills
* [x] Criar Skill de gerenciamento de ambiente
* [x] Skill Linux
* [x] Skill GitHub
* [x] Skill Models
* [ ] Skill Games
* [ ] Skill Mods
* [ ] Permitir criação controlada de novas Skills

---

## FASE 7 — MODEL SCOUT

* [ ] Criar Model Registry
* [ ] Criar pesquisa de modelos
* [ ] Pesquisar Hugging Face
* [ ] Pesquisar GitHub
* [ ] Filtrar candidatos
* [ ] Baixar candidatos
* [ ] Executar benchmark FAST
* [ ] Executar benchmark SMART
* [ ] Comparar com baseline
* [ ] Registrar resultados
* [ ] Criar sistema de candidatos
* [ ] Criar staging
* [ ] Criar rollback

---

## FASE 8 — DESCOBRIR O TETO DO HARDWARE

* [ ] Testar modelos maiores
* [ ] Testar diferentes quantizações
* [ ] Medir VRAM
* [ ] Medir RAM
* [ ] Medir tokens/s
* [ ] Medir contexto
* [ ] Testar CPU offload
* [ ] Testar GPU offload
* [ ] Encontrar maior modelo operacionalmente útil
* [ ] Definir modelo FAST
* [ ] Definir modelo SMART
* [ ] Avaliar necessidade de modelo HEAVY

---

## FASE 9 — INTERFACE WEB

* [ ] Escolher interface/harness web
* [ ] Conectar ao Harness
* [ ] Chat
* [ ] Status de execução
* [ ] Logs
* [ ] Ferramentas utilizadas
* [ ] Confirmações
* [ ] Gerenciamento de tarefas
* [ ] Histórico
* [ ] Monitoramento de modelos

---

## FASE 10 — GUI / VISÃO

Somente depois do sistema principal estar estável.

* [ ] Screenshots
* [ ] Browser automation
* [ ] Mouse
* [ ] Keyboard
* [ ] GUI automation
* [ ] Análise visual
* [ ] Automação de aplicações gráficas

---

# 31. OBJETIVO DO PRIMEIRO DIA

Não tentar terminar o projeto.

O primeiro objetivo é simplesmente:

```text
8B local
    ↓
recebe instrução
    ↓
executa ferramenta
    ↓
recebe resultado
    ↓
continua raciocínio
    ↓
responde ao usuário
```

Este objetivo inicial já foi atingido.

O próximo objetivo é aumentar progressivamente a autonomia do agente.

---

# 32. VISÃO FINAL

A arquitetura desejada:

```text
                         USUÁRIO
                            │
                            ▼
                       WEB UI
                            │
                            ▼
                     ┌────────────┐
                     │   HARNESS  │
                     └─────┬──────┘
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
     MODEL ROUTER       CONTEXT           MEMORY
          │             MANAGER
     ┌────┼────┐
     ▼    ▼    ▼
    8B  SMART  HEAVY
     │    │    │
     └────┼────┘
          │
          ▼
       TOOLS
          │
   ┌──────┼────────┐
   ▼      ▼        ▼
 Files  Terminal   Web
          │
          ▼
        Skills
          │
          ▼
     Task State
          │
          ▼
     Model Scout
          │
          ▼
   Benchmark / Registry
```

---

# 33. PRINCÍPIO FINAL

O objetivo não é encontrar um modelo perfeito.

O objetivo é construir um sistema capaz de:

```text
descobrir
    ↓
testar
    ↓
comparar
    ↓
escolher
    ↓
usar
    ↓
monitorar
    ↓
melhorar
```

O modelo pode mudar.

A quantização pode mudar.

O hardware pode mudar.

As ferramentas podem mudar.

As Skills podem mudar.

O Harness deve continuar funcionando.

> **O agente deve ser maior que o modelo que o executa.**

---

# 34. ESTADO ATUAL DO AMBIENTE

Configuração atualmente conhecida:

* SO: Fedora 44 KDE
* CPU: Ryzen 5 5600G
* GPU: NVIDIA RTX 3070 8 GB
* Backend: Ollama 0.35.1
* Modelo: Qwen3 8B
* Quantização: Q4_K_M
* Tamanho do modelo: aproximadamente 5.2 GB
* VRAM observada durante execução: aproximadamente 5.5 GB
* Execução: GPU NVIDIA

---

# 35. EXPERIMENTOS ARQUITETURAIS

## 35.1 OpenCode

O OpenCode foi avaliado como possível Harness externo.

Objetivo do experimento:

* evitar reconstruir funcionalidades já existentes;
* testar tool calling;
* testar execução autônoma;
* comparar comportamento de modelos;
* avaliar possibilidade de reutilização de um Harness maduro.

Durante os testes:

* Qwen3 8B conseguiu utilizar algumas ferramentas;
* conseguiu ler arquivos;
* conseguiu consultar documentação;
* apresentou dificuldades com seleção/especificação de algumas ferramentas;
* apresentou dificuldades em tarefas multi-etapas;
* em alguns casos interrompeu a execução antes de concluir a tarefa.

Conclusão atual:

> **OpenCode não foi adotado como arquitetura definitiva.**

Ele permanece como alternativa que pode ser reutilizada caso os próximos experimentos demonstrem vantagem suficiente.

A avaliação de uma ferramenta externa não deve alterar o princípio de que o sistema final deve permanecer independente de uma implementação específica de Harness.

---

# 36. ESTADO DE DESENVOLVIMENTO

O projeto já possui uma primeira implementação funcional de um Harness local capaz de:

* receber tarefas;
* manter estado da tarefa;
* selecionar ferramentas;
* validar argumentos;
* executar ferramentas;
* registrar resultados;
* detectar conclusão;
* tratar falhas;
* recuperar de erros simples;
* controlar permissões;
* solicitar confirmação para ações sensíveis;
* cancelar ações;
* aplicar restrições específicas da tarefa;
* executar comandos reais com `shell=False`;
* rejeitar operadores de shell não suportados;
* carregar Skills;
* registrar progresso.

O conjunto automatizado atual possui testes para:

* Task State;
* conclusão;
* falhas;
* cancelamento;
* Permission Manager (incluindo comandos seguros como nvidia-smi e inspeções de cmake/gcc);
* validação de ferramentas;
* execução real de comandos;
* rejeição de comandos compostos;
* argumentos inválidos;
* restrições de tarefa;
* Context Manager e compactação de contexto;
* detecção e bloqueio de loops repetitivos com normalização de argumentos;
* Memória Persistente (CRUD, persistência JSON, injeção de contexto);
* Model Router (roteamento por complexidade e escalada por erros);
* extração e atualização dinâmica do progresso do projeto (Project Progress);
* carregamento e correspondência de Skills;
* ferramentas expandidas (replace_in_file, web_search, fetch_url, save_memory, get_memory).

O estado atual dos testes automatizados é:

```text
68 testes aprovados
```

Esses componentes ainda devem ser considerados **implementação inicial**, não arquitetura final.

A evolução deve continuar sendo orientada pelas tarefas reais que o agente precisa executar.

---

# 37. PRÓXIMO OBJETIVO

O próximo objetivo não é simplesmente implementar mais componentes.

É demonstrar que o agente consegue assumir uma tarefa real de desenvolvimento e executar um ciclo completo:

```text
receber objetivo
      ↓
entender contexto
      ↓
inspecionar projeto
      ↓
planejar
      ↓
selecionar ferramenta
      ↓
executar
      ↓
observar resultado
      ↓
corrigir
      ↓
validar
      ↓
continuar
      ↓
concluir
```

A partir desse teste, os próximos componentes devem ser determinados pela pergunta:

> **O que está impedindo o agente de completar a tarefa sozinho?**

Essa resposta deve orientar a próxima etapa de desenvolvimento.

A arquitetura anteriormente definida como FAST 8B + SMART 14B deve ser
migrada para FAST + SMART.

O tamanho do modelo não define o papel SMART.
14B deve ser apenas uma característica de um candidato, não um requisito.

Antes de continuar o desenvolvimento, atualize a especificação do projeto
para refletir essa decisão e ajuste os arquivos necessários.
Não baixe nenhum modelo.
Depois rode os testes.
