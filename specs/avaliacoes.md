# Avaliações registradas

Gerado em 13/10/2026 08:41 por `scripts/registrar_avaliacoes.py` a partir de: `20261009_200900`.

Uma linha por perfil. "Aprovação" conta só os casos que valem nota (sem os informativos e sem falhas de infraestrutura).

| Categoria | Perfil | Aprovação | Raciocínio | Tarefas reais | Tarefas numeradas | Tarefa 3 | tokens/s | VRAM pico (MB) | RAM livre mín. (MB) |
|---|---|---|---|---|---|---|---|---|---|
| FAST sozinho | 4b | 44/56 (79%) | 9/12 | 12/20 | 4/4 | falhou | 99.2 | 4767.0 | 4152.0 |
| FAST sozinho | 4b-16k-kv8 | 38/56 (68%) | 8/12 | 7/20 | 4/4 | falhou | 97.2 | 4829.0 | 3801.0 |
| FAST sozinho | 9b | 48/56 (86%) | 9/12 | 15/20 | 4/4 | passou | 51.0 | 7170.0 | 522.0 |
| FAST sozinho | 9b-kv8 | 50/56 (89%) | 12/12 | 14/20 | 4/4 | falhou | 63.4 | 7145.0 | 931.0 |
| FAST com think | 9b-think | 47/56 (84%) | 12/12 | 12/20 | 4/4 | falhou | 50.6 | 7147.0 | 422.0 |
| SMART sozinho | s-gptoss20 | 15/20 (75%) | 6/6 | 5/10 | 4/4 | falhou | 30.5 | 6965.0 | 1874.0 |
| Cascata (FAST + SMART) | par-9b+gemma12 | 9/14 (64%) | - | 8/10 | 1/4 | falhou | 61.5 | 7613.0 | 6919.0 |

Categorias sem dados nesta rodada: nenhuma (as quatro foram medidas).

