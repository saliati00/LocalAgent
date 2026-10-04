# Skill: Gestão, Seleção e Benchmark de Modelos Locais

## Objetivo

Instruir o agente sobre o ciclo de vida dos modelos de IA no hardware local
(RTX 3070 8GB VRAM + 16GB RAM), runtimes disponíveis (Ollama e llama.cpp),
níveis de quantização e seleção de modelos para cada papel arquitetural.

---

## Arquitetura de Modelos: FAST e SMART são PAPÉIS, não tamanhos

O projeto utiliza dois papéis arquiteturais. O tamanho do modelo é um
**atributo factual** do candidato — não define o papel.

### FAST (Operador Rápido)
- **Papel**: Operação diária, comandos, leitura de arquivos, tarefas diretas e bootstrap do agente.
- **Modelo atual**: `qwen3:8b` — status `installed` (bootstrap sem lifecycle formal).
  - Nunca passou por `candidate → selected_for_benchmark → adopted`.
  - Permanece como bootstrap até que as Fases 7/8 executem o lifecycle formal do FAST.
- **Qualquer modelo** pode assumir o papel FAST após passar pelo lifecycle.

### SMART (Especialista)
- **Papel**: Tarefas de raciocínio avançado: código complexo, arquitetura, planejamento, escalada.
- **Modelo atual**: Nenhum adotado (`active_smart_model = null`).
- **Qualquer modelo** com capacidade adequada pode ser SMART — o tamanho não é critério.
- Requer aprovação formal no lifecycle antes de ser usado pelo agente.

### Lifecycle obrigatório para ambos os papéis
```
register_model_candidate()       → status: candidate
set_*_candidate_for_benchmark()  → status: selected_for_benchmark
[benchmark real executado]       → evidência documentada
set_active_*_model()             → status: adopted  +  active_*_model atualizado
```

**`selected_for_benchmark` ≠ `adopted`**. Um modelo selecionado para benchmark
ainda não foi adotado e não deve ser usado como modelo ativo.

---

## Hardware Disponível

- **GPU**: NVIDIA RTX 3070 — 8 GB VRAM (CUDA)
- **RAM**: 16 GB sistema
- **Armazenamento**: 263 GB disponíveis em /home

### Estimativa de VRAM por quantização
| Quantização | Modelo ≈8B | Modelo ≈14B |
|-------------|-----------|------------|
| Q4_K_M      | ~5.5 GB   | ~9.0 GB    |
| Q5_K_M      | ~6.5 GB   | ~10.5 GB   |
| Q3_K_M      | ~4.5 GB   | ~7.5 GB    |

Modelos que excedem 8 GB de VRAM operam com offload parcial de camadas para RAM.
Offload parcial é aceito para o papel SMART, mas impacta latência.

---

## Runtimes Locais

### 1. Ollama
- Backend atual rodando em `http://localhost:11434`.
- Listar modelos instalados:
  ```
  run_command(command="ollama list", reason="Verificar modelos instalados no Ollama")
  ```
- **Download de modelo é uma operação sensível.** Exige:
  1. Candidato formalmente registrado no Model Registry com justificativa técnica.
  2. Status `selected_for_benchmark` atribuído explicitamente.
  3. **Autorização/confirmação explícita antes de executar `ollama pull`.**
  - Nunca execute `ollama pull` como consequência automática de `next_action = "Baixar modelo"`.
  - Apresente o candidato selecionado, o registro de evidências e aguarde confirmação.

### 2. llama.cpp
- Permite controle granular de quantização, context shift e offload.
- Indicado para benchmarks avançados e quantização manual de arquivos GGUF.

---

## Quantização

- **Q4_K_M**: Ponto de equilíbrio padrão entre qualidade e VRAM (4 bits).
- **Q5_K_M**: Maior precisão para modelos menores.
- **Q3_K_M / Q4_K_S**: Permite carregar modelos maiores dentro de 8 GB de VRAM com mais offload.

---

## Procedimento do Model Scout (Descoberta → Decisão → Registro)

Ao receber a pendência `"Baixar modelo"` ou qualquer etapa de seleção SMART,
**não execute download imediatamente**. Siga este procedimento:

### Passo 1 — Consultar o Registry existente
```
get_model_registry()
```
Verifique quais candidatos já estão registrados e em qual status.
Se já houver um candidato com `selected_for_benchmark`, ele é o candidato para download.
Se não houver, realize o Passo 2.

### Passo 2 — Filtrar candidatos por hardware
- Critério mínimo: compatibilidade com RTX 3070 (8 GB VRAM) com offload aceitável.
- Verifique disponibilidade real no Ollama (`ollama list`).
- Pesquise releases e especificações com `web_search` e `fetch_url` se necessário.
- Rejeite modelos cujos nomes não existem oficialmente (alucinações).

### Passo 3 — Comparar candidatos com evidência
- Documente pelo menos dois candidatos com justificativa técnica.
- Para cada candidato registre: `size_gb`, `vram_gb`, `description`, `justification`.
- Use `register_model_candidate(name=..., role="smart", ...)`.

### Passo 4 — Selecionar para benchmark (sem baixar ainda)
```
set_smart_candidate_for_benchmark(model_name=..., rationale="...")
```
Isso marca o candidato como `selected_for_benchmark`. **Não baixa o modelo.**

### Passo 5 — Registrar evidências na memória
```
save_memory(category="decisions", key="smart_candidate", value="...", description="...")
```

### Passo 6 — Aguardar autorização para download
Apresente ao usuário:
- Candidato selecionado e por quê.
- Status atual no registry.
- Evidências de hardware fit.
- **Solicite autorização explícita antes de executar qualquer `ollama pull`.**

### Decisão válida: `NO_SUITABLE_CANDIDATE`
Se após pesquisa nenhum candidato for adequado ao hardware, registre:
```
save_memory(category="decisions", key="smart_candidate_status",
            value="NO_SUITABLE_CANDIDATE", description="Motivo: ...")
```
Isso é uma decisão legítima — não force um download sem evidências.

---

## Critérios de Aceitação do Harness

O Harness **não aceitará** marcar `update_spec_checklist("Escolher modelo SMART candidato", True)` se:
- Menos de 2 candidatos SMART registrados com justificativa.
- Nenhum candidato com dados de hardware (`vram_gb`, `size_gb`).
- Modelos alucinados (nomes inexistentes oficialmente).

O Harness **também não deve** tratar `"Baixar modelo"` como autorização automática para
`ollama pull`. Download exige o candidato em `selected_for_benchmark` e confirmação explícita.
