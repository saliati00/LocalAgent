import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from core.harness.stagnation import StagnationDetector, EscalationEvent
from core.harness.task_state import TaskState
from core.router.model_router import ModelRouter


# =========================================================
# TESTE 1: FAST PROGRIDE NORMALMENTE → NÃO ESCALA
# =========================================================

def test_fast_progresses_normally_does_not_escalate():
    """
    Quando o modelo FAST realiza ações reais que progridem o estado
    (como modificar arquivos ou avançar o checklist), o detector
    reconhece progresso real e não escala para SMART.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)
    router = ModelRouter()

    # 1. Leitura inicial (consulta)
    detector.record_action(
        name="get_project_status",
        arguments={},
        result={"success": True, "next_action": "Criar script"},
        current_state={"current_phase": "FASE 1", "next_action": "Criar script"},
    )
    assert detector.stagnation_cycles == 1
    assert not detector.is_stagnated()

    # 2. Ação real: escrever arquivo
    is_prog = detector.record_action(
        name="write_file",
        arguments={"path": "script.py", "content": "print('ok')"},
        result={"success": True},
        current_state={"current_phase": "FASE 1", "next_action": "Criar script"},
    )
    assert is_prog is True
    assert detector.stagnation_cycles == 0
    assert not detector.is_stagnated()

    # 3. Consulta de validação
    detector.record_action(
        name="read_file",
        arguments={"path": "script.py"},
        result={"success": True, "content": "print('ok')"},
        current_state={"current_phase": "FASE 1", "next_action": "Criar script"},
    )
    assert detector.stagnation_cycles == 1

    # 4. Transição real de checklist
    is_prog = detector.record_action(
        name="update_spec_checklist",
        arguments={"item": "Criar script", "completed": True},
        result={"success": True, "next_action": "Testar script"},
        current_state={"current_phase": "FASE 1", "next_action": "Testar script"},
    )
    assert is_prog is True
    assert detector.stagnation_cycles == 0

    escalate, reason = router.should_escalate(
        stagnation_cycles=detector.stagnation_cycles,
        max_stagnation_cycles=detector.max_stagnation_cycles,
    )
    assert escalate is False
    assert reason == ""


# =========================================================
# TESTE 2: FERRAMENTA FALHA → NÃO CONFUNDIR COM ESTAGNAÇÃO
# =========================================================

def test_tool_failure_not_confused_with_reasoning_stagnation():
    """
    Uma ferramenta que falha tecnicamente (ex: comando inválido, arquivo não encontrado)
    deve ser contabilizada como falha de ferramenta e não como ciclo de estagnação de sucesso.
    Não deve gerar escalonamento com motivo de estagnação de raciocínio.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)
    router = ModelRouter()

    # Ferramenta falha tecnicamente
    is_prog = detector.record_action(
        name="run_command",
        arguments={"command": "nonexistent_command", "reason": "teste"},
        result={"success": False, "error": "command not found: nonexistent_command"},
    )
    assert is_prog is False
    assert detector.consecutive_tool_failures == 1
    # Não conta como ciclo de estagnação de sucesso
    assert detector.stagnation_cycles == 0
    assert not detector.is_stagnated()

    # Uma falha técnica isolada não causa escalada por estagnação
    should_esc, reason, _ = detector.check_escalation(fast_model="fast-model:test")
    assert should_esc is False

    # O router também não escala por erro isolado nem por estagnação
    escalate, esc_reason = router.should_escalate(
        consecutive_errors=detector.consecutive_tool_failures,
        stagnation_cycles=detector.stagnation_cycles,
        max_stagnation_cycles=detector.max_stagnation_cycles,
    )
    assert escalate is False


# =========================================================
# TESTE 3: REPETIÇÃO SEM MUDANÇA → ESCALA APÓS THRESHOLD
# =========================================================

def test_repeated_tools_without_state_change_escalates_after_threshold():
    """
    Ferramentas executadas repetidamente com sucesso, mas sem qualquer
    mudança de estado/progresso real, atingem o threshold e escalam para SMART.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)
    router = ModelRouter()

    # Simula 5 consultas consecutivas com sucesso (abaixo do threshold 6)
    query_tools = [
        ("get_project_status", {}),
        ("get_model_registry", {}),
        ("read_file", {"path": "specs/projeto.md", "start_line": 1, "end_line": 20}),
        ("get_memory", {"category": "decisions"}),
        ("get_model_registry", {"role": "smart"}),
    ]

    for tool_name, args in query_tools:
        is_prog = detector.record_action(
            name=tool_name,
            arguments=args,
            result={"success": True, "data": "dummy"},
            current_state={"current_phase": "FASE 2", "next_action": "Escolher modelo"},
        )
        assert is_prog is False

    assert detector.stagnation_cycles == 5
    assert not detector.is_stagnated()

    # 6ª consulta consecutiva atinge o threshold (6)
    detector.record_action(
        name="get_project_status",
        arguments={},
        result={"success": True},
        current_state={"current_phase": "FASE 2", "next_action": "Escolher modelo"},
    )
    assert detector.stagnation_cycles == 6
    assert detector.is_stagnated()

    should_esc, reason, event = detector.check_escalation(
        phase="FASE 2",
        task="Escolher modelo smart",
        fast_model="qwen3:8b",
        iteration=8,
    )
    assert should_esc is True
    assert "Estagnação de raciocínio do modelo FAST ('qwen3:8b')" in reason
    assert event is not None
    assert event.event == "ESCALATE_TO_SMART"
    assert event.stagnation_cycles == 6


# =========================================================
# TESTE 4: SAVE_MEMORY REPETIDO NÃO CONTA COMO PROGRESSO
# =========================================================

def test_repeated_save_memory_does_not_count_as_progress():
    """
    Regra 9: save_memory() sozinho NÃO deve ser considerado progresso
    se não houver mudança de estado/objetivo.
    Mesmo executando com sucesso 6 vezes, o detector escala por estagnação.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)

    for i in range(6):
        is_prog = detector.record_action(
            name="save_memory",
            arguments={
                "category": "notes",
                "key": f"analysis_{i}",
                "value": "Analisando opções sem decidir",
            },
            result={"success": True, "saved": True},
            current_state={"current_phase": "FASE 2", "next_action": "Escolher modelo"},
        )
        assert is_prog is False
        assert detector.stagnation_cycles == i + 1

    assert detector.stagnation_cycles == 6
    assert detector.is_stagnated()

    should_esc, reason, event = detector.check_escalation(
        phase="FASE 2",
        task="Escolher modelo",
        fast_model="qwen3:8b",
        iteration=7,
    )
    assert should_esc is True
    assert event.event == "ESCALATE_TO_SMART"


# =========================================================
# TESTE 5: TRANSIÇÃO REAL REINICIA CONTADOR DE ESTAGNAÇÃO
# =========================================================

def test_real_state_transition_resets_stagnation_counter():
    """
    Uma transição real de estado (ex: avanço de checklist ou fase)
    deve zerar o contador de ciclos de estagnação.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)

    # 4 consultas sem progresso
    for _ in range(4):
        detector.record_action(
            name="get_project_status",
            arguments={},
            result={"success": True},
            current_state={"current_phase": "FASE 2", "next_action": "Ação A"},
        )
    assert detector.stagnation_cycles == 4

    # Transição real: checklist atualizado avançando a próxima ação
    is_prog = detector.record_action(
        name="update_spec_checklist",
        arguments={"item": "Ação A", "completed": True},
        result={"success": True, "next_action": "Ação B"},
        current_state={"current_phase": "FASE 2", "next_action": "Ação B"},
    )
    assert is_prog is True
    assert detector.stagnation_cycles == 0
    assert not detector.is_stagnated()

    # Mais 3 consultas: totaliza 3 (abaixo do limiar 6)
    for _ in range(3):
        detector.record_action(
            name="get_model_registry",
            arguments={},
            result={"success": True},
            current_state={"current_phase": "FASE 2", "next_action": "Ação B"},
        )
    assert detector.stagnation_cycles == 3
    assert not detector.is_stagnated()


# =========================================================
# TESTE 6: ESCALONAMENTO GERA EVENTO/ESTADO ESCALATE_TO_SMART
# =========================================================

def test_escalation_generates_escalate_to_smart_event_and_state():
    """
    O escalonamento gera o estado e evento explícito ESCALATE_TO_SMART no TaskState
    com todos os campos diagnósticos obrigatórios.
    """
    detector = StagnationDetector(max_stagnation_cycles=6)
    state = TaskState("Executar FASE 2")
    state.set_progress(phase="FASE 2", next_action="Baixar modelo")

    # Acumula 6 ciclos de estagnação
    for _ in range(6):
        detector.record_action(
            name="get_model_registry",
            arguments={},
            result={"success": True},
            current_state={"current_phase": "FASE 2", "next_action": "Baixar modelo"},
        )

    should_esc, reason, event = detector.check_escalation(
        phase=state.current_phase,
        task=state.task,
        fast_model="custom-fast:7b",
        iteration=12,
        last_action=state.last_tool,
    )
    assert should_esc is True
    assert event is not None

    state.escalate_to_smart(event, reason=reason)

    assert state.status == "escalate_to_smart"
    assert state.is_escalated is True
    assert state.escalation_event is not None
    assert state.escalation_event["event"] == "ESCALATE_TO_SMART"
    assert state.escalation_event["phase"] == "FASE 2"
    assert state.escalation_event["task"] == "Executar FASE 2"
    assert state.escalation_event["fast_model"] == "custom-fast:7b"
    assert state.escalation_event["iterations"] == 12
    assert state.escalation_event["stagnation_cycles"] == 6
    assert isinstance(state.escalation_event["repeated_tools"], list)
    assert state.escalation_event["reason"] == reason

    # Resumo reflete os novos campos
    summary = state.summary()
    assert summary["status"] == "escalate_to_smart"
    assert summary["is_escalated"] is True
    assert summary["escalation_event"]["event"] == "ESCALATE_TO_SMART"

    # Step gravado no histórico
    assert any(step["type"] == "escalate_to_smart" for step in state.steps)


# =========================================================
# TESTE 7: NENHUM MODELO SMART É SELECIONADO OU ADOTADO
# =========================================================

def test_escalation_does_not_select_or_adopt_smart_model(tmp_path):
    """
    Regra 1 e 3: O mecanismo de escalonamento NÃO escolhe nem adota
    nenhum modelo SMART no registry. O active_smart_model permanece inalterado (null).
    """
    reg_file = tmp_path / "registry.json"
    reg_data = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {"role": "smart", "status": "candidate"},
            "qwen2.5:14b": {"role": "smart", "status": "candidate"},
        },
    }
    reg_file.write_text(json.dumps(reg_data))
    router = ModelRouter(registry_path=reg_file)

    detector = StagnationDetector(max_stagnation_cycles=6)
    for _ in range(6):
        detector.record_action(
            name="get_project_status",
            arguments={},
            result={"success": True},
        )

    escalate, reason = router.should_escalate(
        stagnation_cycles=detector.stagnation_cycles,
        max_stagnation_cycles=detector.max_stagnation_cycles,
    )
    assert escalate is True

    # O registry permanece estritamente com active_smart_model = null
    assert router.get_smart_model() is None
    loaded = json.loads(reg_file.read_text())
    assert loaded["active_smart_model"] is None


# =========================================================
# TESTE 8: NENHUM DOWNLOAD É EXECUTADO NO ESCALONAMENTO
# =========================================================

def test_escalation_does_not_execute_download(tmp_path, monkeypatch):
    """
    Regra 2: Nenhum download é executado durante o processo de detecção
    ou acionamento do escalonamento.
    """
    download_called = False

    def mock_download(*args, **kwargs):
        nonlocal download_called
        download_called = True
        return {"success": True}

    monkeypatch.setattr("tools.web.download_file", mock_download)

    detector = StagnationDetector(max_stagnation_cycles=6)
    for _ in range(6):
        detector.record_action(
            name="get_model_registry",
            arguments={},
            result={"success": True},
        )

    should_esc, reason, event = detector.check_escalation(
        phase="FASE 2",
        task="Tarefa",
        fast_model="fast-m",
        iteration=6,
    )
    assert should_esc is True
    assert download_called is False


# =========================================================
# TESTE 9: NENHUM CANDIDATO É ALTERADO PARA SELECTED_FOR_BENCHMARK
# =========================================================

def test_escalation_does_not_change_candidate_status(tmp_path):
    """
    Regra 4: Nenhum candidato SMART tem seu status alterado para
    'selected_for_benchmark' durante a detecção ou emissão do ESCALATE_TO_SMART.
    """
    reg_file = tmp_path / "registry.json"
    initial_registry = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {"role": "smart", "status": "candidate"},
            "qwen2.5:14b": {"role": "smart", "status": "candidate"},
        },
    }
    reg_file.write_text(json.dumps(initial_registry))
    router = ModelRouter(registry_path=reg_file)

    detector = StagnationDetector(max_stagnation_cycles=6)
    for _ in range(6):
        detector.record_action(
            name="read_file",
            arguments={"path": "specs/models.md"},
            result={"success": True, "content": "..."},
        )

    escalate, reason = router.should_escalate(
        stagnation_cycles=detector.stagnation_cycles,
        max_stagnation_cycles=detector.max_stagnation_cycles,
    )
    assert escalate is True

    # Verifica o registry
    current_reg = json.loads(reg_file.read_text())
    for m_name, m_info in current_reg["models"].items():
        assert m_info["status"] == "candidate"
        assert m_info["status"] != "selected_for_benchmark"


# =========================================================
# TESTE 10: MECANISMO FUNCIONA INDEPENDENTE DE NOMES DE MODELOS
# =========================================================

def test_escalation_mechanism_is_model_agnostic(tmp_path):
    """
    Regra 5 e 10: O mecanismo funciona para qualquer modelo FAST arbitrário
    (ex: 'llama-small:1b', 'mistral-mini:3b') e qualquer candidato SMART arbitrário,
    sem nenhum hardcode de nomes ou tamanhos específicos (como '14b', 'qwen').
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "my-arbitrary-fast-model:2b",
        "active_smart_model": None,
        "models": {
            "candidate-alpha-arbitrary": {"role": "smart", "status": "candidate"},
            "candidate-beta-arbitrary": {"role": "smart", "status": "candidate"},
        },
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_fast_model() == "my-arbitrary-fast-model:2b"

    detector = StagnationDetector(max_stagnation_cycles=6)
    for _ in range(6):
        detector.record_action(
            name="get_project_status",
            arguments={},
            result={"success": True},
        )

    should_esc, reason, event = detector.check_escalation(
        phase="FASE X",
        task="Qualquer tarefa genérica",
        fast_model="my-arbitrary-fast-model:2b",
        iteration=9,
    )
    assert should_esc is True
    assert event.fast_model == "my-arbitrary-fast-model:2b"
    assert "14b" not in reason.lower()
    assert "qwen" not in reason.lower()
    assert "my-arbitrary-fast-model:2b" in reason


# =========================================================
# TESTE 11: INTEGRAÇÃO COM AGENT.PY (ENCERRA LIMPO SEM 31 ITERAÇÕES)
# =========================================================

def test_agent_integration_halts_cleanly_on_stagnation(tmp_path, monkeypatch):
    """
    Testa o fluxo real de agent.py:
    Quando o modelo FAST entra em repetição de consultas (como no teste real de 26 ferramentas),
    o Harness detecta a estagnação e encerra a execução registrando ESCALATE_TO_SMART,
    sem atingir o limite de 31 iterações.
    """
    import agent
    from types import SimpleNamespace

    # Mock de mensagens de tool calls repetidas
    def make_tool_call_response():
        tool_call = SimpleNamespace(
            function=SimpleNamespace(
                name="get_project_status",
                arguments={},
            )
        )
        msg = SimpleNamespace(
            role="assistant",
            content="",
            tool_calls=[tool_call],
        )
        return SimpleNamespace(
            message=msg,
            prompt_eval_count=10,
            eval_count=5,
        )

    call_count = 0

    def mock_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_tool_call_response()

    monkeypatch.setattr(agent.client, "chat", mock_chat)

    tasks_dir = tmp_path / "tasks"
    monkeypatch.setattr("agent.Path", lambda p: tasks_dir if "tasks" in str(p) else Path(p))

    # Executa o agente
    agent.agent("Tarefa de teste de estagnação")

    # Verifica que NÃO executou 31 iterações
    # Com default_max_stagnation_cycles=6, deve encerrar bem antes de 31
    assert call_count <= 8
    assert call_count >= 6

    # Verifica que o estado salvo em tasks/ possui status smart_unavailable
    task_files = list(tasks_dir.glob("task_*.json"))
    assert len(task_files) >= 1
    task_data = json.loads(task_files[-1].read_text(encoding="utf-8"))
    assert task_data["status"] == "smart_unavailable"
    assert task_data["is_escalated"] is True
    assert task_data["escalation_event"]["event"] == "ESCALATE_TO_SMART"
    assert task_data["smart_status"] == "SMART_UNAVAILABLE"
    assert task_data["is_smart_available"] is False
    assert task_data["smart_diagnostic"]["event"] == "SMART_UNAVAILABLE"
    assert task_data["escalation_event"]["stagnation_cycles"] >= 6


# =========================================================
# TRATAMENTO DE ESCALATE_TO_SMART: DISPONIBILIDADE DO SMART
# =========================================================

def test_escalate_to_smart_with_active_smart_null_yields_smart_unavailable(tmp_path):
    """
    1. ESCALATE_TO_SMART + active_smart_model = null → SMART_UNAVAILABLE.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {"role": "smart", "status": "candidate"},
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    is_available, reason, diag = router.check_smart_availability()
    assert is_available is False
    assert diag["event"] == "SMART_UNAVAILABLE"
    assert diag["active_smart_model"] is None
    assert diag["is_installed"] is False
    assert diag["required_capability"] == "select_and_prepare_smart"

    state = TaskState("Tarefa de teste")
    state.resolve_escalation_smart_unavailable(diag, reason=reason)
    assert state.status == "smart_unavailable"
    assert state.smart_status == "SMART_UNAVAILABLE"
    assert state.is_smart_available is False


def test_escalate_to_smart_with_smart_adopted_and_installed_yields_smart_available(tmp_path):
    """
    2. ESCALATE_TO_SMART + SMART adotado e instalado → SMART_AVAILABLE.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "custom-smart:20b",
        "models": {
            "custom-smart:20b": {
                "name": "custom-smart:20b",
                "role": "smart",
                "status": "installed",
            },
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    # Mock do backend confirmando que custom-smart:20b está instalado
    backend_checker = lambda model: model == "custom-smart:20b"
    is_available, reason, diag = router.check_smart_availability(backend_checker=backend_checker)

    assert is_available is True
    assert diag["event"] == "SMART_AVAILABLE"
    assert diag["active_smart_model"] == "custom-smart:20b"
    assert diag["is_installed"] is True
    assert diag["required_capability"] is None

    state = TaskState("Tarefa de teste")
    state.resolve_escalation_smart_available(diag, reason=reason)
    assert state.status == "smart_available"
    assert state.smart_status == "SMART_AVAILABLE"
    assert state.is_smart_available is True


def test_active_smart_pointing_to_nonexistent_model_yields_smart_unavailable(tmp_path):
    """
    3. active_smart_model apontando para modelo inexistente → SMART_UNAVAILABLE.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "phantom-model:70b",
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)

    is_available, reason, diag = router.check_smart_availability()
    assert is_available is False
    assert diag["event"] == "SMART_UNAVAILABLE"
    assert diag["is_installed"] is False
    assert "phantom-model:70b" in reason


def test_model_registered_as_candidate_is_not_available_smart(tmp_path):
    """
    4. Modelo registrado como candidate → não é SMART disponível.
    Mesmo que active_smart_model aponte para um candidato, seu status='candidate'
    impede que ele seja considerado SMART_AVAILABLE.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "candidate-model:14b",
        "models": {
            "candidate-model:14b": {
                "name": "candidate-model:14b",
                "role": "smart",
                "status": "candidate",
            },
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    # Mesmo que o modelo estivesse baixado no backend
    backend_checker = lambda model: True
    is_available, reason, diag = router.check_smart_availability(backend_checker=backend_checker)

    assert is_available is False
    assert diag["event"] == "SMART_UNAVAILABLE"
    assert "status 'candidate'" in reason


def test_model_selected_for_benchmark_is_not_available_smart(tmp_path):
    """
    5. Modelo selected_for_benchmark, mas ainda não adotado → não é SMART disponível.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "bench-model:14b",
        "models": {
            "bench-model:14b": {
                "name": "bench-model:14b",
                "role": "smart",
                "status": "selected_for_benchmark",
            },
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    backend_checker = lambda model: True
    is_available, reason, diag = router.check_smart_availability(backend_checker=backend_checker)

    assert is_available is False
    assert diag["event"] == "SMART_UNAVAILABLE"
    assert "status 'selected_for_benchmark'" in reason


def test_smart_available_does_not_trigger_download(tmp_path, monkeypatch):
    """
    6. SMART disponível não dispara download.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "installed-smart:14b",
        "models": {
            "installed-smart:14b": {
                "role": "smart",
                "status": "installed",
            },
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    download_called = False
    def mock_download(*args, **kwargs):
        nonlocal download_called
        download_called = True
        return {"success": True}

    monkeypatch.setattr("tools.web.download_file", mock_download)

    is_available, _, _ = router.check_smart_availability(backend_checker=lambda m: True)
    assert is_available is True
    assert download_called is False


def test_smart_unavailable_does_not_select_candidate(tmp_path):
    """
    7. SMART indisponível não seleciona candidato.
    """
    reg_file = tmp_path / "registry.json"
    initial_reg = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "cand-1": {"role": "smart", "status": "candidate"},
            "cand-2": {"role": "smart", "status": "candidate"},
        },
    }
    reg_file.write_text(json.dumps(initial_reg))
    router = ModelRouter(registry_path=reg_file)

    is_available, _, _ = router.check_smart_availability()
    assert is_available is False

    # Nenhum candidato deve ter mudado de status
    current_reg = json.loads(reg_file.read_text())
    assert current_reg["models"]["cand-1"]["status"] == "candidate"
    assert current_reg["models"]["cand-2"]["status"] == "candidate"


def test_smart_unavailable_does_not_alter_registry(tmp_path):
    """
    8. SMART indisponível não altera o Registry.
    """
    reg_file = tmp_path / "registry.json"
    initial_content = json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "cand-1": {"role": "smart", "status": "candidate"},
        },
    }, indent=2)
    reg_file.write_text(initial_content)
    router = ModelRouter(registry_path=reg_file)

    router.check_smart_availability()

    # O conteúdo do arquivo permanece idêntico
    assert reg_file.read_text() == initial_content


def test_persisted_state_contains_structured_diagnostic():
    """
    9. O estado persistido contém diagnóstico estruturado completo:
    - FAST que estava executando;
    - motivo da escalada;
    - active_smart_model;
    - se o modelo está instalado;
    - próxima capacidade necessária;
    - fase/tarefa atual.
    """
    state = TaskState("Tarefa de desenvolvimento")
    state.set_progress(phase="FASE 2", next_action="Baixar modelo")

    diag = {
        "event": "SMART_UNAVAILABLE",
        "fast_model": "qwen3:8b",
        "escalation_reason": "Estagnação detectada: 6 ciclos sem progresso",
        "active_smart_model": None,
        "is_installed": False,
        "required_capability": "select_and_prepare_smart",
        "phase": "FASE 2",
        "task": "Tarefa de desenvolvimento",
    }

    state.resolve_escalation_smart_unavailable(diag, reason="SMART ausente")
    summary = state.summary()

    assert summary["status"] == "smart_unavailable"
    assert summary["smart_status"] == "SMART_UNAVAILABLE"
    assert summary["is_smart_available"] is False
    assert summary["smart_diagnostic"]["fast_model"] == "qwen3:8b"
    assert summary["smart_diagnostic"]["escalation_reason"] == "Estagnação detectada: 6 ciclos sem progresso"
    assert summary["smart_diagnostic"]["active_smart_model"] is None
    assert summary["smart_diagnostic"]["is_installed"] is False
    assert summary["smart_diagnostic"]["required_capability"] == "select_and_prepare_smart"
    assert summary["smart_diagnostic"]["phase"] == "FASE 2"
    assert summary["smart_diagnostic"]["task"] == "Tarefa de desenvolvimento"


def test_execution_does_not_end_in_generic_failure():
    """
    10. A execução não termina simplesmente como uma falha genérica (failed)
    quando o motivo é ausência de SMART.
    """
    state = TaskState("Tarefa teste")
    diag = {
        "event": "SMART_UNAVAILABLE",
        "active_smart_model": None,
        "is_installed": False,
        "required_capability": "select_and_prepare_smart",
    }
    state.resolve_escalation_smart_unavailable(diag, reason="SMART não configurado")

    # Não deve ser 'failed'
    assert state.status != "failed"
    assert state.status == "smart_unavailable"
    assert state.current_step != "Tarefa falhou"
    assert not any(step["type"] == "task_error" for step in state.steps)
    assert any(step["type"] == "smart_unavailable" for step in state.steps)


def test_smart_availability_mechanism_is_model_agnostic(tmp_path):
    """
    11. O mecanismo continua independente do nome/tamanho do modelo:
    funciona com qualquer nome de modelo FAST e SMART sem hardcodes.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "any-fast-operator:1b",
        "active_smart_model": "arbitrary-smart-specialist:50b",
        "models": {
            "arbitrary-smart-specialist:50b": {
                "role": "smart",
                "status": "installed",
            },
        },
    }))
    router = ModelRouter(registry_path=reg_file)

    backend_checker = lambda m: m == "arbitrary-smart-specialist:50b"
    is_available, reason, diag = router.check_smart_availability(backend_checker=backend_checker)

    assert is_available is True
    assert diag["event"] == "SMART_AVAILABLE"
    assert diag["active_smart_model"] == "arbitrary-smart-specialist:50b"
    assert "14b" not in reason.lower()
    assert "qwen" not in reason.lower()



