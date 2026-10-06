from types import SimpleNamespace

from core.harness.handover import build_handover_packet
from core.harness.memo import ToolMemo
from core.harness.repetition import RepeatedResponseDetector
from core.harness.task_state import TaskState


# ---------------------------------------------------------
# Pacote de passagem
# ---------------------------------------------------------

def _history():
    messages = [
        {"role": "system", "content": "SYSTEM " * 500},
        {"role": "user", "content": "pedido original"},
    ]
    for i in range(12):
        messages.append(SimpleNamespace(role="assistant", content="", tool_calls=[object()]))
        messages.append({
            "role": "tool",
            "tool_name": "get_project_status",
            "content": f"{{'success': True, 'n': {i}}}",
        })
    messages.append({
        "role": "tool",
        "tool_name": "update_spec_checklist",
        "content": "{'success': False, 'error': 'critério não atendido'}",
    })
    return messages


def test_handover_packet_is_short_and_has_the_essentials():
    packet = build_handover_packet(
        goal="Selecionar modelo SMART",
        from_model="fast-x",
        to_model="smart-y",
        reason="6 ciclos sem progresso",
        messages=_history(),
        actions_completed=[f"acao {i}" for i in range(20)],
        phase="FASE 2",
        next_action="Baixar modelo",
    )

    assert "Selecionar modelo SMART" in packet
    assert "fast-x" in packet and "smart-y" in packet
    assert "6 ciclos sem progresso" in packet
    assert "Baixar modelo" in packet
    assert "critério não atendido" in packet
    assert "acao 19" in packet and "acao 0" not in packet
    assert "SYSTEM SYSTEM" not in packet
    assert len(packet) <= 3500


def test_handover_packet_is_truncated_to_the_limit():
    packet = build_handover_packet(
        goal="x" * 10_000, from_model="a", to_model="b", reason="r" * 5000,
        messages=_history(), max_chars=800,
    )
    assert len(packet) <= 800


# ---------------------------------------------------------
# Memoização
# ---------------------------------------------------------

def test_memo_returns_cached_read_only_result_with_notice():
    memo = ToolMemo()
    memo.record("get_model_registry", {"role": "smart"}, {"success": True, "models": {}})

    hit = memo.lookup("get_model_registry", {"role": "smart"})

    assert hit["cached"] is True
    assert "nada mudou" in hit["notice"]
    assert memo.lookup("get_model_registry", {"role": "fast"}) is None
    assert memo.hits == 1


def test_memo_ignores_argument_order():
    memo = ToolMemo()
    memo.record("get_memory", {"category": "a", "key": "b"}, {"success": True})
    assert memo.lookup("get_memory", {"key": "b", "category": "a"}) is not None


def test_memo_invalidated_by_mutating_tools():
    memo = ToolMemo()
    memo.record("get_project_status", {}, {"success": True})
    memo.record("update_spec_checklist", {"item": "x"}, {"success": True})
    assert memo.lookup("get_project_status", {}) is None


def test_memo_does_not_cache_failures_or_mutating_tools():
    memo = ToolMemo()
    memo.record("read_file", {"path": "a"}, {"success": False, "error": "x"})
    memo.record("write_file", {"path": "a", "content": "c"}, {"success": True})
    assert memo.lookup("read_file", {"path": "a"}) is None
    assert memo.lookup("write_file", {"path": "a", "content": "c"}) is None


# ---------------------------------------------------------
# Respostas repetidas
# ---------------------------------------------------------

def test_repeated_responses_are_detected_after_threshold():
    detector = RepeatedResponseDetector(threshold=3)
    text = "A tarefa não pode ser concluída sem a senha de administrador. Execute manualmente."

    assert detector.check(text) is False
    assert detector.check(text + " ") is False
    assert detector.check(text.upper()) is True


def test_different_responses_are_not_flagged():
    detector = RepeatedResponseDetector(threshold=3)

    assert detector.check("Listei os arquivos do diretório.") is False
    assert detector.check("Agora vou rodar os testes.") is False
    assert detector.check("Os testes passaram, atualizando o checklist.") is False


# ---------------------------------------------------------
# Estado
# ---------------------------------------------------------

def test_task_state_needs_human_is_distinct_from_cancelled():
    state = TaskState("t")
    state.needs_human("precisa da senha de administrador")

    summary = state.summary()

    assert summary["status"] == "needs_human"
    assert summary["needs_human_reason"] == "precisa da senha de administrador"
    assert state.status != "cancelled"
