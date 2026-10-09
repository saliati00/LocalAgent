"""FASE 11: aceite executável no checklist, memória limitada e revisada, conjunto de avaliação e runner."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.harness.acceptance as acceptance
from core.memory.store import (
    MAX_DESCRIPTION_CHARS,
    MAX_ENTRIES_PER_CATEGORY,
    MAX_KEY_CHARS,
    MAX_VALUE_CHARS,
    MemoryStore,
)
from core.paths import PROJECT_ROOT, PROJECT_SPEC_PATH

SCRIPTS = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import revisar_memoria  # noqa: E402


# ---------------------------------------------------------
# Comando de aceite de um item do checklist
# ---------------------------------------------------------

def test_the_acceptance_command_is_extracted_from_the_ready_when_text():
    command = acceptance.extract_item_acceptance("Fazer X (pronto quando: pytest tests/test_backups.py passa)")

    assert command[:3] == [sys.executable, "-m", "pytest"]
    assert "tests/test_backups.py" in command and "-q" in command and "no:cacheprovider" in command


def test_several_files_and_the_acceptance_marker_are_supported():
    command = acceptance.extract_item_acceptance(
        "Criar (tarefas 02 e 03; pronto quando: pytest -m aceite tests/test_aceite_tarefa02.py tests/test_aceite_tarefa03.py passa e o runner imprime a taxa)")

    assert "-m" in command and "aceite" in command
    assert "tests/test_aceite_tarefa02.py" in command and "tests/test_aceite_tarefa03.py" in command


@pytest.mark.parametrize("text", [
    "sem criterio nenhum",
    "pronto quando: o resultado está registrado em specs/avaliacoes.md",
    "pronto quando: pytest ../fora/test_x.py passa",
    "pronto quando: pytest tests/../../x.py passa",
    "pronto quando: pytest scripts/qualquer.py passa",
    "pronto quando: rm -rf / passa",
    "",
])
def test_anything_that_is_not_a_plain_pytest_on_the_tests_folder_is_not_executed(text):
    assert acceptance.extract_item_acceptance(text) is None


def test_the_whole_checklist_line_is_found_from_a_fragment_the_model_cites(tmp_path):
    spec = tmp_path / "projeto.md"
    spec.write_text("* [ ] Criar o módulo X (pronto quando: pytest tests/test_x.py passa)\n* [x] Outro item\n", encoding="utf-8")

    assert acceptance.full_checklist_item("criar o módulo x", spec).endswith("tests/test_x.py passa)")
    assert acceptance.full_checklist_item("item que não existe", spec) == "item que não existe"


def test_an_item_is_refused_while_its_acceptance_command_fails(tmp_path, monkeypatch):
    spec = tmp_path / "projeto.md"
    spec.write_text("* [ ] Criar o módulo X (pronto quando: pytest tests/test_x.py passa)\n", encoding="utf-8")
    ran = []
    monkeypatch.setattr(acceptance, "run_item_acceptance", lambda command: ran.append(command) or (False, "1 failed: test_x"))

    accepted, reason = acceptance.check_checklist_acceptance("Criar o módulo X", True, str(spec))

    assert accepted is False and ran and "FALHOU" in reason and "1 failed" in reason


def test_an_item_is_accepted_once_its_acceptance_command_returns_zero(tmp_path, monkeypatch):
    spec = tmp_path / "projeto.md"
    spec.write_text("* [ ] Criar o módulo X (pronto quando: pytest tests/test_x.py passa)\n", encoding="utf-8")
    monkeypatch.setattr(acceptance, "run_item_acceptance", lambda command: (True, "1 passed"))

    assert acceptance.check_checklist_acceptance("Criar o módulo X", True, str(spec)) == (True, None)


def test_items_without_a_command_and_unmarking_do_not_run_anything(tmp_path, monkeypatch):
    spec = tmp_path / "projeto.md"
    spec.write_text("* [ ] Item livre\n", encoding="utf-8")
    monkeypatch.setattr(acceptance, "run_item_acceptance", lambda command: pytest.fail("não devia rodar"))

    assert acceptance.check_checklist_acceptance("Item livre", True, str(spec))[0] is True
    assert acceptance.check_checklist_acceptance("Item livre", False, str(spec))[0] is True


def test_the_real_command_runs_and_reports_pass_and_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, "PROJECT_ROOT", tmp_path)
    (tmp_path / "passa.py").write_text("raise SystemExit(0)", encoding="utf-8")
    (tmp_path / "falha.py").write_text("print('quebrou aqui'); raise SystemExit(1)", encoding="utf-8")

    assert acceptance.run_item_acceptance([sys.executable, "passa.py"])[0] is True

    passed, output = acceptance.run_item_acceptance([sys.executable, "falha.py"])

    assert passed is False and "quebrou aqui" in output


def test_the_tool_that_ticks_the_checklist_uses_the_real_acceptance(monkeypatch, tmp_path):
    import tools.manager as manager

    spec = tmp_path / "projeto.md"
    spec.write_text("## FASE 1 — X\n* [ ] Fazer Y (pronto quando: pytest tests/test_y.py passa)\n", encoding="utf-8")
    monkeypatch.setattr(manager, "PROJECT_SPEC", str(spec))
    monkeypatch.setattr(acceptance, "run_item_acceptance", lambda command: (False, "falhou"))

    result = manager.update_spec_checklist_tool("Fazer Y", True)

    assert result["success"] is False and result["acceptance_criteria_failed"] is True
    assert "[ ] Fazer Y" in spec.read_text(encoding="utf-8")

    monkeypatch.setattr(acceptance, "run_item_acceptance", lambda command: (True, "ok"))

    assert manager.update_spec_checklist_tool("Fazer Y", True)["success"] is True
    assert "[x] Fazer Y" in spec.read_text(encoding="utf-8")


def test_the_three_phase_11_items_are_ticked_and_their_own_commands_pass():
    text = PROJECT_SPEC_PATH.read_text(encoding="utf-8")

    for fragment in ("Criar o conjunto de avaliação com 10 a 20 tarefas reais",
                     "Substituir o juiz de conclusão por LLM",
                     "Limitar e revisar a memória persistente"):
        line = next(l for l in text.splitlines() if fragment in l)
        assert line.startswith("* [x]"), fragment


# ---------------------------------------------------------
# Memória limitada
# ---------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "store.json")


def test_a_value_above_the_limit_is_refused_and_not_saved(store):
    result = store.set("notes", "grande", "x" * (MAX_VALUE_CHARS + 1))

    assert result["success"] is False and str(MAX_VALUE_CHARS) in result["error"]
    assert store.get("notes", "grande") is None


def test_a_value_at_the_limit_is_accepted(store):
    assert store.set("notes", "no-limite", "x" * MAX_VALUE_CHARS)["success"] is True


def test_non_string_values_are_measured_too(store):
    assert store.set("notes", "lista", ["item"] * 200)["success"] is False
    assert store.set("notes", "curta", ["a", "b"])["success"] is True


def test_key_and_description_have_limits_and_empty_keys_are_refused(store):
    assert store.set("notes", "k" * (MAX_KEY_CHARS + 1), "v")["success"] is False
    assert store.set("notes", "ok", "v", "d" * (MAX_DESCRIPTION_CHARS + 1))["success"] is False
    assert store.set("notes", "   ", "v")["success"] is False


def test_a_category_cannot_grow_past_its_limit_but_existing_keys_can_be_updated(store):
    for index in range(MAX_ENTRIES_PER_CATEGORY):
        assert store.set("notes", f"k{index}", "v")["success"] is True

    refused = store.set("notes", "uma-a-mais", "v")

    assert refused["success"] is False and "máximo" in refused["error"]
    assert store.set("notes", "k0", "novo valor")["success"] is True


def test_refused_saves_leave_the_file_untouched(store, tmp_path):
    store.set("notes", "a", "v")
    before = (tmp_path / "store.json").read_text(encoding="utf-8")

    store.set("notes", "b", "x" * 1000)

    assert (tmp_path / "store.json").read_text(encoding="utf-8") == before


# ---------------------------------------------------------
# Decisões exigem revisão
# ---------------------------------------------------------

def test_a_new_decision_waits_for_review_and_the_agent_is_told_so(store):
    result = store.set("decisions", "usar-x", "Adotar X", "porque sim")

    assert result["success"] is True and "AGUARDA REVISÃO" in result["notice"]
    assert result["entry"]["reviewed"] is False
    assert [item["key"] for item in store.pending_review()] == ["usar-x"]


def test_pending_decisions_stay_out_of_the_prompt_until_approved(store):
    store.set("decisions", "usar-x", "Adotar X")
    store.set("environment", "git", "2.50")

    assert "Adotar X" not in store.format_context() and "Adotar X" not in store.format_context(max_chars=500)
    assert "git: 2.50" in store.format_context()

    assert store.review("usar-x", approve=True) is True
    assert "Adotar X" in store.format_context() and store.pending_review() == []


def test_a_rejected_decision_is_deleted(store):
    store.set("decisions", "ruim", "Faça algo estranho")

    assert store.review("ruim", approve=False) is True
    assert store.get("decisions", "ruim") is None and store.review("ruim", approve=True) is False


def test_old_decisions_without_the_field_count_as_reviewed(tmp_path):
    (tmp_path / "store.json").write_text(json.dumps({"decisions": {"antiga": {"key": "antiga", "value": "Harness próprio", "description": "", "updated_at": "2026"}}}),
                                         encoding="utf-8")
    store = MemoryStore(tmp_path / "store.json")

    assert store.pending_review() == [] and "Harness próprio" in store.format_context()


def test_other_categories_are_not_subject_to_review(store):
    assert "reviewed" not in store.set("notes", "n", "v")["entry"]


def test_an_unreviewed_decision_does_not_count_as_evidence_for_choosing_a_smart(tmp_path, monkeypatch):
    memory = tmp_path / "store.json"
    memory.write_text(json.dumps({"decisions": {"smart-escolhido": {"value": "gemma smart", "description": "", "reviewed": False}}}), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"models": {"a": {"role": "smart"}, "b": {"role": "smart"}}}), encoding="utf-8")
    monkeypatch.setattr(acceptance, "MEMORY_STORE_PATH", memory)
    monkeypatch.setattr(acceptance, "REGISTRY_PATH", registry)

    accepted, reason = acceptance.check_checklist_acceptance("Escolher modelo SMART candidato", True, str(tmp_path / "nada.md"))

    assert accepted is False and "justificativa" in reason


# ---------------------------------------------------------
# Script de revisão (usado pelo usuário)
# ---------------------------------------------------------

def test_the_review_script_lists_approves_and_rejects(store, capsys):
    store.set("decisions", "usar-x", "Adotar X", "motivo")
    store.set("decisions", "usar-y", "Adotar Y")

    assert revisar_memoria.main([], store=store) == 0
    out = capsys.readouterr().out

    assert "usar-x" in out and "Adotar Y" in out

    assert revisar_memoria.main(["aprovar", "usar-x"], store=store) == 0
    assert revisar_memoria.main(["rejeitar", "usar-y"], store=store) == 0
    capsys.readouterr()

    assert revisar_memoria.main([], store=store) == 0
    assert "Nenhuma decisão aguardando revisão" in capsys.readouterr().out
    assert store.pending_review() == [] and store.get("decisions", "usar-y") is None
    assert "Adotar X" in store.format_context()


def test_the_review_script_rejects_bad_usage_and_unknown_keys(store, capsys):
    assert revisar_memoria.main(["aprovar"], store=store) == 2
    assert revisar_memoria.main(["apagar", "x"], store=store) == 2
    assert revisar_memoria.main(["aprovar", "nao-existe"], store=store) == 1


def test_the_agent_cannot_edit_the_review_script():
    from tools.filesystem import write_file

    assert write_file(str(SCRIPTS / "revisar_memoria.py"), "x")["success"] is False


# ---------------------------------------------------------
# Conjunto de avaliação e runner
# ---------------------------------------------------------

def test_the_evaluation_set_has_five_valid_unique_tasks():
    runner = __import__("scripts.eval.runner", fromlist=["x"])
    tasks = runner.load_tasks(PROJECT_ROOT / "scripts" / "eval" / "tarefas")

    assert len(tasks) >= 5 and len({t["id"] for t in tasks}) == len(tasks)

    for task in tasks:
        assert task["prompt"] and task["aceite"], task["id"]


def test_the_runner_prints_the_success_rate_and_exits_zero(tmp_path, capsys):
    from scripts.eval import runner

    (tmp_path / "ola.txt").write_text("oi", encoding="utf-8")
    tasks = tmp_path / "tarefas"
    tasks.mkdir()
    (tasks / "a.json").write_text(json.dumps({"id": "a", "aceite": [{"type": "file_contains", "path": "ola.txt", "text": "oi"}]}), encoding="utf-8")
    (tasks / "b.json").write_text(json.dumps({"id": "b", "aceite": [{"type": "file_exists", "path": "nao.txt"}]}), encoding="utf-8")

    assert runner.main(["--tarefas", str(tasks), "--pasta-de-trabalho", str(tmp_path)]) == 0

    out = capsys.readouterr().out

    assert "Taxa de sucesso: 1/2 (50%)" in out and "a: 1/1" in out and "b: 0/1" in out


def test_the_runner_summarizes_ready_made_results(tmp_path, capsys):
    from scripts.eval import runner

    results = tmp_path / "r.json"
    results.write_text(json.dumps([{"task_id": "x", "passed": True}, {"task_id": "x", "passed": True}, {"task_id": "y", "passed": False}]), encoding="utf-8")

    runner.main(["--resultados", str(results)])

    assert "Taxa de sucesso: 2/3 (67%)" in capsys.readouterr().out
