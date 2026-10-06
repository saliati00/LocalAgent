# AMBIENTE — hardware e sistema de referência

> Este arquivo descreve a máquina em que o agente roda. Atualize-o ao trocar de computador.
> O Harness não lê este arquivo; ele existe para o usuário e para a documentação (`specs/projeto.md`, capítulos 3, 34 e 40).

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
* Modelo SMART: ainda não adotado (`active_smart_model` é `null`). Não é baixado pelo instalador.

## Atenção: dados antigos

* `memory/store.json` (categoria `environment`) foi preenchido no Fedora e ainda cita caminhos como `/usr/bin/git`, `.venv/bin/cmake` e "263 GB em /home". No computador novo, peça ao agente para verificar o ambiente de novo (a ferramenta `check_tools` e a Skill `windows` ajudam) ou limpe essas entradas.
* `models/registry.json` marca o `qwen3:8b` como `installed`. O Harness confere com `ollama list`, então a marcação só vale se o modelo foi baixado de fato.

## Como medir (para atualizar os números do capítulo 40)

1. Rode algumas tarefas reais e leia as linhas `PROMPT_SIZES` e `TOKENS` em `logs/agent.log`.
2. Com o Ollama aberto, `ollama ps` mostra quanto de cada modelo está na GPU e quanto está na CPU.
3. Anote tokens por segundo e tempo de troca FAST ↔ SMART antes de decidir qualquer cascata.
