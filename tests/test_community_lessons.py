"""Lições da comunidade (OpenHands, SWE-agent, Goose/Ollama): limiares de travamento,
detecção de truncamento de contexto, tetos de leitura, validação de sintaxe e varredura de Skills."""

import shutil
from types import SimpleNamespace

import pytest

import agent
from core.context.manager import ContextManager
from core.context.metrics import context_pressure
from core.harness import logger
from core.harness.stagnation import StagnationDetector
from core.paths import TMP_ROOT
from core.skills.proposal import build_skill_text
from core.skills.validator import validate_skill_text
from tools.filesystem import (
    MAX_LIST_ITEMS,
    MAX_READ_CHARS,
    list_directory,
    read_file,
    replace_in_file,
    write_file,
)


@pytest.fixture
def scratch():
    path = TMP_ROOT / "localagent_lessons_tests"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------
# Detector de travamento
# ---------------------------------------------------------

def fail(detector, name="run_command", command="x"):
    detector.record_action(name, {"command": command, "reason": "r"}, {"success": False, "error": "e"})


def ok(detector, name, **arguments):
    return detector.record_action(name, arguments, {"success": True})


def test_same_action_failing_three_times_is_stuck():
    detector = StagnationDetector()

    fail(detector)
    fail(detector)
    assert detector.is_stagnated() is False

    fail(detector)

    assert detector.is_stagnated() is True
    escalate, reason, _ = detector.check_escalation(fast_model="fast")
    assert escalate is True
    assert "Travamento" in reason and "falhou 3 vezes" in reason


def test_different_failures_are_not_stuck():
    detector = StagnationDetector()

    fail(detector, command="a")
    fail(detector, command="b")
    fail(detector, command="c")

    assert detector.is_stagnated() is False


def test_alternating_two_actions_is_stuck_after_six_cycles():
    detector = StagnationDetector(max_stagnation_cycles=99)

    for index in range(6):
        if index % 2 == 0:
            ok(detector, "get_project_status")
        else:
            ok(detector, "get_memory", category="notes")

    assert detector.is_stagnated() is True
    assert "alternando" in detector.stuck_reason


def test_non_alternating_sequence_is_not_flagged():
    detector = StagnationDetector(max_stagnation_cycles=99)

    ok(detector, "get_project_status")
    ok(detector, "get_memory", category="a")
    ok(detector, "get_project_status")
    ok(detector, "list_directory", path="x")
    ok(detector, "get_project_status")
    ok(detector, "get_memory", category="a")

    assert detector.stuck_reason is None


def test_reset_clears_stuck_state():
    detector = StagnationDetector()
    for _ in range(3):
        fail(detector)

    detector.reset()

    assert detector.is_stagnated() is False
    assert detector.stuck_reason is None
    assert detector.signatures == []


# ---------------------------------------------------------
# Truncamento de contexto
# ---------------------------------------------------------

@pytest.mark.parametrize("tokens, expected", [
    (1000, "ok"),
    (7000, "ok"),
    (7800, "near_limit"),
    (8185, "truncated"),
    (8192, "truncated"),
])
def test_context_pressure_levels(tokens, expected):
    assert context_pressure(tokens, 8192) == expected


def test_request_compaction_forces_one_compaction():
    manager = ContextManager(max_context_chars=10**9)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    messages += [{"role": "tool", "tool_name": "t", "content": f"r{i}"} for i in range(10)]

    assert manager.prepare_messages(messages) is messages

    manager.request_compaction()
    compacted = manager.prepare_messages(messages)

    assert len(compacted) < len(messages)
    assert manager.compaction_requested is False


def test_agent_logs_and_reacts_to_a_near_full_prompt(tmp_path, monkeypatch):
    responses = iter([
        SimpleNamespace(
            message=SimpleNamespace(role="assistant", content="Pronto.", tool_calls=None),
            prompt_eval_count=8190,
            eval_count=5,
        ),
    ])

    monkeypatch.setattr(agent.client, "chat", lambda *a, **k: next(responses))
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "check_completion", lambda **kw: {"status": "complete", "reason": "ok"})

    agent.agent("Diga pronto")

    assert "CONTEXT_TRUNCATED" in logger.LOG_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------
# Tetos de leitura
# ---------------------------------------------------------

def test_read_file_caps_large_files_and_hints_line_ranges(scratch):
    big = scratch / "grande.txt"
    big.write_text("linha de texto\n" * 2000, encoding="utf-8")

    result = read_file(str(big))

    assert result["success"] is True
    assert result["truncated"] is True
    assert len(result["content"]) <= MAX_READ_CHARS
    assert "start_line" in result["notice"]
    assert result["total_lines"] == 2000


def test_read_file_line_range_is_also_capped(scratch):
    big = scratch / "grande.txt"
    big.write_text(("x" * 100 + "\n") * 500, encoding="utf-8")

    result = read_file(str(big), start_line=1, end_line=500)

    assert result["truncated"] is True
    assert len(result["content"]) <= MAX_READ_CHARS


def test_small_files_are_untouched(scratch):
    small = scratch / "pequeno.txt"
    small.write_text("oi", encoding="utf-8")

    result = read_file(str(small))

    assert result["content"] == "oi"
    assert "truncated" not in result


def test_list_directory_is_capped(scratch):
    for index in range(MAX_LIST_ITEMS + 30):
        (scratch / f"f{index:04d}.txt").write_text("", encoding="utf-8")

    result = list_directory(str(scratch))

    assert len(result["items"]) == MAX_LIST_ITEMS
    assert result["truncated"] is True
    assert result["total_items"] == MAX_LIST_ITEMS + 30


# ---------------------------------------------------------
# Validação de sintaxe Python (guardrail do SWE-agent)
# ---------------------------------------------------------

def test_write_file_rejects_invalid_python_and_creates_nothing(scratch):
    target = scratch / "quebrado.py"

    result = write_file(str(target), "def f(:\n    pass\n")

    assert result["success"] is False
    assert result["syntax_error"] is True
    assert "linha 1" in result["error"]
    assert not target.exists()


def test_write_file_accepts_valid_python_and_other_file_types(scratch):
    assert write_file(str(scratch / "ok.py"), "x = 1\n")["success"] is True
    assert write_file(str(scratch / "nota.txt"), "def f(:")["success"] is True


def test_replace_in_file_rejects_edit_that_breaks_python(scratch):
    target = scratch / "mod.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = replace_in_file(str(target), "return 1", "return (")

    assert result["success"] is False
    assert result["syntax_error"] is True
    assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"

    assert replace_in_file(str(target), "return 1", "return 2")["success"] is True


# ---------------------------------------------------------
# Varredura extra no validador de Skills
# ---------------------------------------------------------

def good_text():
    return build_skill_text(
        name="checar-release",
        description="Verifica release nova.",
        triggers=["release", "github"],
        when_to_use="Quando perguntarem por versão nova.",
        steps=["Buscar a página.", "Comparar versões."],
        validation="Cita as duas versões.",
        limits="Não instala nada.",
    )


def test_clean_skill_still_passes():
    ok_, errors = validate_skill_text("checar-release", good_text())
    assert ok_ is True, errors


@pytest.mark.parametrize("payload, fragment", [
    ("texto​oculto", "invisíveis"),
    ("texto‮sobrescrito", "invisíveis"),
    ("QWxhZGRpbjpvcGVuIHNlc2FtZVNlZ3JlZG9RV2xoWkdScGJqcHY=", "base64"),
    ("veja https://exemplo.com/instalar", "URLs"),
])
def test_validator_rejects_hidden_payloads(payload, fragment):
    text = good_text().replace("Não instala nada.", "Não instala nada. " + payload)

    ok_, errors = validate_skill_text("checar-release", text)

    assert ok_ is False
    assert any(fragment in error for error in errors), errors
