import pytest

from core.harness.task_state import TaskState
from core.harness.permissions import (
    parse_command,
    requires_confirmation,
)
from tools.manager import validate_arguments


# =========================================================
# TASK STATE
# =========================================================

def test_task_state_initial():

    state = TaskState(
        "Teste inicial"
    )

    assert state.status == "running"
    assert state.tool_calls == 0
    assert state.successful_tools == 0
    assert state.failed_tools == 0
    assert state.current_step is None
    assert state.next_action is None


def test_task_state_complete():

    state = TaskState(
        "Teste de conclusão"
    )

    state.set_progress(
        current_step="Executando teste",
        next_action="Validar resultado",
    )

    state.complete()

    assert state.status == "completed"
    assert state.current_step == "Tarefa concluída"
    assert state.next_action is None


def test_task_state_fail():

    state = TaskState(
        "Teste de falha"
    )

    state.fail(
        "Erro proposital"
    )

    assert state.status == "failed"
    assert state.current_step == "Tarefa falhou"
    assert state.next_action is None
    assert state.steps[-1]["type"] == "task_error"


def test_task_state_block():

    state = TaskState(
        "Teste de bloqueio"
    )

    state.block(
        "Bloqueado pelo Harness"
    )

    assert state.status == "blocked"
    assert state.current_step == "Tarefa bloqueada"
    assert state.next_action is None
    assert state.steps[-1]["type"] == "task_blocked"
    assert state.is_blocked is True
    assert state.block_reason == "Bloqueado pelo Harness"


def test_task_state_cancel():

    state = TaskState(
        "Teste de cancelamento"
    )

    state.cancel(
        "Cancelado pelo usuário"
    )

    assert state.status == "cancelled"
    assert state.current_step == "Ação cancelada"
    assert state.next_action is None
    assert state.steps[-1]["type"] == "task_cancelled"


def test_task_state_tool_success():

    state = TaskState(
        "Teste de ferramenta"
    )

    state.start_tool(
        "list_directory",
        {"path": "/tmp"},
    )

    result = {
        "success": True,
        "items": [],
    }

    state.finish_tool(
        "list_directory",
        result,
    )

    assert state.tool_calls == 1
    assert state.successful_tools == 1
    assert state.failed_tools == 0
    assert state.last_tool == "list_directory"
    assert state.last_tool_success is True
    assert state.status == "running"


def test_task_state_tool_failure():

    state = TaskState(
        "Teste de falha de ferramenta"
    )

    state.start_tool(
        "read_file",
        {"path": "/arquivo/inexistente"},
    )

    result = {
        "success": False,
        "error": "Arquivo não encontrado",
    }

    state.finish_tool(
        "read_file",
        result,
    )

    assert state.tool_calls == 1
    assert state.successful_tools == 0
    assert state.failed_tools == 1
    assert state.last_tool == "read_file"
    assert state.last_tool_success is False


# =========================================================
# PERMISSION MANAGER
# =========================================================

def test_parse_safe_command():

    parts, error = parse_command(
        "uname -a"
    )

    assert error is None
    assert parts == [
        "uname",
        "-a",
    ]


@pytest.mark.parametrize(
    "command",
    [
        "ls | grep teste",
        "ls || echo teste",
        "ls && echo teste",
        "ls; echo teste",
        "ls > arquivo.txt",
        "cat < arquivo.txt",
        "echo $(whoami)",
        "echo `whoami`",
        "sleep 1 &",
    ],
)
def test_reject_shell_operators(command):

    parts, error = parse_command(
        command
    )

    assert parts is None
    assert error is not None


def test_safe_command_does_not_require_confirmation():

    assert (
        requires_confirmation(
            "uname -a"
        )
        is False
    )


def test_sensitive_command_requires_confirmation():

    assert (
        requires_confirmation(
            "sudo dnf install git"
        )
        is True
    )


def test_safe_git_command():

    assert (
        requires_confirmation(
            "git status"
        )
        is False
    )


def test_sensitive_git_command():

    assert (
        requires_confirmation(
            "git push"
        )
        is True
    )


def test_safe_pip_command():
    assert requires_confirmation("pip list") is False
    assert requires_confirmation("pip --version") is False


def test_sensitive_pip_command():
    assert requires_confirmation("pip install requests") is True


def test_safe_ollama_command():
    assert requires_confirmation("ollama list") is False


def test_safe_pytest_command():
    assert requires_confirmation("pytest -v") is False


def test_safe_nvidia_smi():
    assert requires_confirmation("nvidia-smi") is False


def test_safe_cmake_command():
    assert requires_confirmation("cmake --version") is False
    assert requires_confirmation("cmake -v") is False


def test_safe_gcc_command():
    assert requires_confirmation("gcc --version") is False
    assert requires_confirmation("g++ --version") is False


def test_safe_make_command():
    assert requires_confirmation("make --version") is False


def test_safe_curl_command():
    assert requires_confirmation("curl --version") is False


# =========================================================
# TOOL MANAGER
# =========================================================

def test_valid_read_file_arguments():

    valid, error = validate_arguments(
        "read_file",
        {
            "path": "/tmp/teste",
        },
    )

    assert valid is True
    assert error == ""


def test_unknown_tool_argument():

    valid, error = validate_arguments(
        "read_file",
        {
            "path": "/tmp/teste",
            "foo": "bar",
        },
    )

    assert valid is False
    assert "foo" in error


def test_missing_required_argument():

    valid, error = validate_arguments(
        "run_command",
        {
            "command": "pwd",
        },
    )

    assert valid is False
    assert "reason" in error


def test_valid_run_command_arguments():

    valid, error = validate_arguments(
        "run_command",
        {
            "command": "pwd",
            "reason": "Verificar diretório atual",
        },
    )

    assert valid is True
    assert error == ""


def test_unknown_tool():

    valid, error = validate_arguments(
        "ferramenta_inexistente",
        {},
    )

    assert valid is False
    assert "desconhecida" in error

# =========================================================
# RUN COMMAND — EXECUÇÃO REAL
# =========================================================

from tools.terminal import run_command


def test_run_command_safe():

    result = run_command(
        "python --version",
        "Verificar a versão do Python",
    )

    assert result["success"] is True
    assert result["returncode"] == 0
    assert "Python" in (result["stdout"] + result["stderr"])


def test_run_command_rejects_pipeline():

    result = run_command(
        "ls | grep teste",
        "Testar rejeição de comando composto",
    )

    assert result["success"] is False
    assert result["tool_error"] is True
    assert "operador" in result["error"]


def test_run_command_requires_reason():

    result = run_command(
        "uname -a",
        "",
    )

    assert result["success"] is False
    assert result["tool_error"] is True
    assert "justificativa" in result["error"]


def test_run_command_rejects_empty_command():

    result = run_command(
        "",
        "Testar comando vazio",
    )

    assert result["success"] is False
    assert result["tool_error"] is True


def test_check_completion_blocks_on_tool_failure():
    from core.harness.completion import check_completion

    comp = check_completion(
        model="dummy",
        task="Baixar modelo SMART",
        response="A ferramenta foi executada mas deu erro.",
        tool_calls=1,
        successful_tools=0,
        failed_tools=1,
        actions_completed=[],
        last_tool_success=False,
        last_failure_reason="A ferramenta falhou",
    )
    assert comp["status"] == "continue"
    assert "erro ou bloqueio recente" in comp["reason"]


def test_check_completion_blocks_on_loop_blocked_response():
    from core.harness.completion import check_completion

    comp = check_completion(
        model="dummy",
        task="Baixar modelo SMART",
        response="A ferramenta update_spec_checklist foi bloqueada pelo Harness para evitar loops de repetição.",
        tool_calls=3,
        successful_tools=2,
        failed_tools=1,
        actions_completed=["update_spec_checklist: ..."],
        last_tool_success=True,
    )
    assert comp["status"] == "continue"
    assert "bloqueio por repetição" in comp["reason"]


# =========================================================
# TESTES DE ORIENTAÇÃO OPERACIONAL DE CONTINUAÇÃO (HARNESS)
# =========================================================

def test_continuation_guidance_when_smart_candidate_exists_and_none_selected(tmp_path):
    """
    Quando há SMART candidate registrado e nenhum selected_for_benchmark,
    a orientação deve indicar explicitamente a transição candidate → selected_for_benchmark
    e referenciar a ferramenta apropriada (set_smart_candidate_for_benchmark).
    """
    import json
    from core.harness.completion import get_continuation_guidance, build_continuation_reason

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "any-model-a:14b": {
                "name": "any-model-a:14b",
                "role": "smart",
                "status": "candidate",
            },
            "any-model-b:20b": {
                "name": "any-model-b:20b",
                "role": "smart",
                "status": "candidate",
            },
        },
    }), encoding="utf-8")

    guidance = get_continuation_guidance(registry_path=reg_file)
    assert guidance is not None
    assert "ESTADO ATUAL" in guidance
    assert "SMART candidate ainda não foi selecionado para benchmark" in guidance
    assert "PRÓXIMA TRANSIÇÃO" in guidance
    assert "candidate → selected_for_benchmark" in guidance
    assert "AÇÃO ESPERADA" in guidance
    assert "set_smart_candidate_for_benchmark" in guidance
    assert "NO_SUITABLE_CANDIDATE" in guidance
    assert "NÃO fique apenas consultando novamente registry/status/memory" in guidance

    # Não deve ter hardcode de modelos específicos
    assert "qwen2.5-coder:14b" not in guidance

    # build_continuation_reason deve incluir a orientação
    reason = build_continuation_reason(
        current_phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Baixar modelo",
        registry_path=reg_file,
    )
    assert "candidate → selected_for_benchmark" in reason
    assert "set_smart_candidate_for_benchmark" in reason


def test_continuation_guidance_suppressed_when_selected_for_benchmark_exists(tmp_path):
    """
    Quando um modelo já está com status 'selected_for_benchmark', a orientação de
    transição preliminar (candidate → selected_for_benchmark) não deve ser exibida.
    """
    import json
    from core.harness.completion import get_continuation_guidance, build_continuation_reason

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "some-model:14b": {
                "name": "some-model:14b",
                "role": "smart",
                "status": "selected_for_benchmark",
            },
        },
    }), encoding="utf-8")

    guidance = get_continuation_guidance(registry_path=reg_file)
    assert guidance is None

    reason = build_continuation_reason(
        current_phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Baixar modelo",
        registry_path=reg_file,
    )
    assert "candidate → selected_for_benchmark" not in reason


def test_continuation_guidance_suppressed_when_smart_model_adopted(tmp_path):
    """
    Quando um modelo SMART já foi formalmente adotado (active_smart_model ou status adopted),
    a orientação de transição preliminar não deve ser exibida.
    """
    import json
    from core.harness.completion import get_continuation_guidance, build_continuation_reason

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "adopted-smart:14b",
        "models": {
            "adopted-smart:14b": {
                "name": "adopted-smart:14b",
                "role": "smart",
                "status": "adopted",
            },
        },
    }), encoding="utf-8")

    guidance = get_continuation_guidance(registry_path=reg_file)
    assert guidance is None

    reason = build_continuation_reason(
        current_phase="FASE 3 — BENCHMARK",
        next_action="Executar benchmark",
        registry_path=reg_file,
    )
    assert "candidate → selected_for_benchmark" not in reason


def test_continuation_guidance_suppressed_when_no_smart_candidates(tmp_path):
    """
    Quando não há candidatos SMART registrados, a orientação de transição
    candidate → selected_for_benchmark não deve ser exibida.
    """
    import json
    from core.harness.completion import get_continuation_guidance

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen3:8b": {
                "name": "Qwen3 8B",
                "role": "fast",
                "status": "installed",
            },
        },
    }), encoding="utf-8")

    guidance = get_continuation_guidance(registry_path=reg_file)
    assert guidance is None


def test_check_completion_enriches_continue_with_guidance(tmp_path):
    """
    check_completion deve enriquecer o motivo de continuação com a orientação determinística
    quando a tarefa não foi concluída e o registry estiver no estado de candidatos pendentes.
    """
    import json
    from core.harness.completion import check_completion

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "candidate-x:14b": {
                "name": "candidate-x:14b",
                "role": "smart",
                "status": "candidate",
            },
        },
    }), encoding="utf-8")

    comp = check_completion(
        model="dummy",
        task="Continuar desenvolvimento",
        response="Executou consulta",
        tool_calls=1,
        successful_tools=1,
        failed_tools=0,
        actions_completed=["get_model_registry: {}"],
        last_tool_success=False,
        last_failure_reason="Ação não concluiu a transição",
        current_phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Baixar modelo",
        registry_path=reg_file,
    )

    assert comp["status"] == "continue"
    assert "candidate → selected_for_benchmark" in comp["reason"]
    assert "set_smart_candidate_for_benchmark" in comp["reason"]


def test_agent_integration_continuation_reason_branch(tmp_path, monkeypatch):
    """
    Testa o caminho real usado em agent.py para dev tasks:
    build_continuation_reason(current_phase=state.current_phase, next_action=state.next_action)
    deve entregar a orientação operacional ao modelo em vez da string estática pura.
    """
    import json
    from core.harness.completion import build_continuation_reason
    from core.harness.task_state import TaskState

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "candidate-model:14b": {
                "name": "candidate-model:14b",
                "role": "smart",
                "status": "candidate",
            },
        },
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.completion.REGISTRY_PATH", reg_file)

    state = TaskState("Continue o desenvolvimento conforme specs/projeto.md.")
    state.set_progress(
        phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Analisar resultado e decidir próxima ação",
    )

    # Simula exatamente o que agent.py executa:
    completion_reason = build_continuation_reason(
        current_phase=state.current_phase,
        next_action=state.next_action,
    )

    # Mensagem final que agent.py monta para o modelo
    model_message_content = f"""
A tarefa ainda não foi concluída.
Status do Harness:
{completion_reason}
"""

    # Prova que a mensagem agora contém a nova orientação operacional e não apenas a string estática
    assert "ESTADO ATUAL" in model_message_content
    assert "SMART candidate ainda não foi selecionado para benchmark" in model_message_content
    assert "PRÓXIMA TRANSIÇÃO" in model_message_content
    assert "candidate → selected_for_benchmark" in model_message_content
    assert "set_smart_candidate_for_benchmark" in model_message_content
    assert "NO_SUITABLE_CANDIDATE" in model_message_content


def test_agent_integration_continuation_suppressed_after_advance(tmp_path, monkeypatch):
    """
    Quando o modelo avançar para selected_for_benchmark, o branch de agent.py
    deve suprimir a orientação preliminar de candidate → selected_for_benchmark.
    """
    import json
    from core.harness.completion import build_continuation_reason
    from core.harness.task_state import TaskState

    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "candidate-model:14b": {
                "name": "candidate-model:14b",
                "role": "smart",
                "status": "selected_for_benchmark",
            },
        },
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.completion.REGISTRY_PATH", reg_file)

    state = TaskState("Continue o desenvolvimento conforme specs/projeto.md.")
    state.set_progress(
        phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Baixar modelo",
    )

    completion_reason = build_continuation_reason(
        current_phase=state.current_phase,
        next_action=state.next_action,
    )

    assert "candidate → selected_for_benchmark" not in completion_reason
    assert "set_smart_candidate_for_benchmark" not in completion_reason
    assert "O projeto possui a pendência ativa 'Baixar modelo'" in completion_reason
