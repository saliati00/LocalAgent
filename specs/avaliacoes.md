# Avaliações registradas

Gerado em 15/10/2026 08:08 por `scripts/registrar_avaliacoes.py` a partir de: `20261014_231448`.

Uma linha por perfil. "Aprovação" conta só os casos que valem nota (sem os informativos e sem falhas de infraestrutura).

| Categoria | Perfil | Aprovação | Raciocínio | Tarefas reais | Tarefas numeradas | Tarefa 3 | tokens/s | VRAM pico (MB) | RAM livre mín. (MB) |
|---|---|---|---|---|---|---|---|---|---|
| FAST sozinho | 9b-16k-kv8 | 50/56 (89%) | 10/12 | 17/20 | 4/4 | falhou | 43.1 | 7157.0 | 1769.0 |
| FAST sozinho | 9b-kv8 | 53/56 (95%) | 12/12 | 17/20 | 4/4 | passou | 63.1 | 7229.0 | 2364.0 |
| SMART sozinho | s-gemma12 | 15/18 (83%) | 5/6 | 8/10 | 2/2 | - | 28.2 | 7629.0 | 178.0 |
| SMART sozinho | s-gptoss20 | 18/20 (90%) | 6/6 | 8/10 | 4/4 | falhou | 31.2 | 6872.0 | 2698.0 |
| Cascata (FAST + SMART) | par-9b+gemma12 | 14/14 (100%) | - | 10/10 | 4/4 | falhou | 62.4 | 7546.0 | 8308.0 |
| Cascata (FAST + SMART) | par-9b+gptoss20 | 13/14 (93%) | - | 10/10 | 3/4 | falhou | 61.7 | 7080.0 | 3556.0 |

Categorias sem dados nesta rodada: FAST com think

