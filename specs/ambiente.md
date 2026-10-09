# AMBIENTE — hardware e sistema de referência

> Este arquivo descreve a máquina em que o agente roda. Atualize-o ao trocar de computador.
> O Harness não lê este arquivo; ele existe para o usuário e para a documentação (`specs/projeto.md`, capítulos 3, 34 e 39; e o capítulo 40 de `specs/historico.md`).

## Hardware de referência (informado pelo usuário e registrado na memória do agente)

* CPU: AMD Ryzen 5 5600G (6 núcleos, 12 threads)
* GPU: NVIDIA GeForce RTX 3070, 8 GB de VRAM
* RAM: 16 GB
* Disco: NVMe
* Sistema alvo: Windows 10/11 (o projeto nasceu no Fedora KDE e foi portado)

## Software

* Python 3.10 ou mais novo (instalador usa o 3.12)
* Ollama (backend de modelos)
* Modelo FAST: o definido em `models/registry.json` (`active_fast_model`, hoje `qwen3:8b`, ~5,2 GB, ~5,5 GB de VRAM)
* Candidatos a FAST: `qwen3.5:9b` e `qwen3.5:4b`. Candidatos a SMART: `gemma4:12b` e `gpt-oss:20b`. Nenhum SMART adotado ainda (`active_smart_model` é `null`); quem decide é a bateria (`comparar.bat`), e o instalador não baixa SMART.

## Dados antigos (resolvido em 09/10/2026)

* A memória do agente (`memory/store.json`) tinha fatos do Fedora (caminhos como `/usr/bin/git` e `/home/...`) e decisões de modelos já superadas (SMART `qwen2.5:14b`, FAST `llama3.2:3b`), que iam para o prompt a cada tarefa. Foram removidos; ficaram CPU, GPU, RAM, sistema (Windows) e as decisões de arquitetura. Os modelos ativos ficam só em `models/registry.json`.
* `models/registry.json` marca o `qwen3:8b` como `installed`. O Harness confere com `ollama list`, então a marcação só vale se o modelo foi baixado.

## Como medir (para atualizar os números do capítulo 40)

1. Rode algumas tarefas reais e leia as linhas `PROMPT_SIZES` e `TOKENS` em `logs/agent.log`.
2. Com o Ollama aberto, `ollama ps` mostra quanto de cada modelo está na GPU e quanto está na CPU.
3. Anote tokens por segundo e tempo de troca FAST ↔ SMART antes de decidir qualquer cascata.
