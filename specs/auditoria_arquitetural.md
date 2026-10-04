AUDITORIA ARQUITETURAL — 03/10/2026

STATUS: PENDENTE
PRIORIDADE: BLOQUEANTE
REGRA: NÃO implementar Scout/Planner/Sandbox/novo backend antes de resolver os hotfixes abaixo.

HOTFIX 0 — Diagnóstico
[ ] Logar run_id em cada linha
[ ] Logar tamanho das seções do prompt

HOTFIX 1 — Contrato de Tools
[ ] Garantir schema == dispatch
[ ] Expor set_smart_candidate_for_benchmark ao modelo
[ ] Criar teste de contrato

HOTFIX 2 — Progresso/Stagnation
[ ] Separar project_next_action de step_hint
[ ] Detector deve observar mudança verificável de estado
[ ] Replay do ciclo de 19:14 deve escalar em <10 iterações

HOTFIX 3 — Proteção de arquivos
[ ] Impedir tools genéricas de escrever:
    specs/projeto.md
    models/registry.json
    memory/store.json
    core/harness/*
    tests/*
    [demais paths a definir]
[ ] Teste write_file → specs/projeto.md deve ser negado

DEPOIS DOS HOTFIXES
[ ] Executar 3–5 runs reais de baseline
[ ] Caracterizar gate/completion/constraint/SMART
[ ] Extrair loop para máquina de estados
[ ] Implementar NEEDS_HUMAN ≠ CANCELLED

ARQUIVOS A AUDITAR ANTES DE IMPLEMENTAR
[ ] core/context/manager.py
[ ] core/harness/acceptance.py
[ ] tools/models.py
[ ] core/harness/project_progress.py
[ ] tools/terminal.py
[ ] tools/web.py
[ ] core/router/model_router.py

REGRAS
- Não implementar nada antes de confirmar os achados.
- Não afirmar comportamento de arquivo não auditado.
- Um commit por mudança.
- Suíte completa passando após cada mudança.
- Cada etapa precisa ter um teste que falhava antes e passa depois.
- Não criar segundo backend, ULTRASMART, Scout automatizado ou abstrações novas sem problema observado em run real.
- Não renomear coisas sem necessidade.
- Não misturar movimentação estrutural com alteração comportamental.
