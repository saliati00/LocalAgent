"""Correções motivadas pelo primeiro log real (07/10/2026): juiz LLM errando, regravação em
loop, tarefa do usuário executada pelo agente, adoção de modelo sem benchmark e erros de
sintaxe/comando que o modelo não conseguia interpretar."""

import os
import sys
from types import SimpleNamespace

import pytest

import agent
import core.tasks as tasks
import tools.manager as manager
from core.context.metrics import estimate_tokens
from core.harness import logger
from core.harness.stagnation import MAX_PROGRESS_WRITES_PER_PATH, StagnationDetector
from core.paths import PROJECT_ROOT
from tools.filesystem import write_file


# ---------------------------------------------------------
# Dono da tarefa e aceite executável (arquivos reais)
# ---------------------------------------------------------

def test_real_task_owners():
    assert [tasks.task_owner(n) for n in (1, 2, 3)] == ["agente"] * 3
    assert [tasks.task_owner(n) for n in (4, 5)] == ["usuario"] * 2


def test_user_tasks_are_not_executed_by_the_agent():
    ok, message = tasks.build_task_prompt(4, "dê continuidade à tarefa 4")

    assert ok is False
    assert "SUA" in message and "ROTEIRO-DE-TESTES.md" in message
    assert agent.resolve_prompt("dê continuidade à tarefa 4") is None
    assert agent.resolve_prompt("@tarefa5") is None


@pytest.mark.parametrize("number", [1, 2, 3])
def test_agent_tasks_declare_a_runnable_acceptance_command(number):
    command = tasks.acceptance_command(number)

    assert command[:4] == [sys.executable, "-m", "pytest", "-m"]
    assert f"tests/test_aceite_tarefa{number:02d}.py" in command
    assert (PROJECT_ROOT / f"tests/test_aceite_tarefa{number:02d}.py").exists()


def test_human_tasks_have_no_acceptance_command():
    assert tasks.acceptance_command(4) is None
    assert tasks.acceptance_command(5) is None


def test_only_the_expected_acceptance_command_shape_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "TAREFAS_DIR", tmp_path)

    def task(text):
        (tmp_path / "tarefa-09-x.md").write_text(f"# Tarefa 09\nQuem faz: agente\n\n## Pronto quando\n{text}\n", encoding="utf-8")
        return tasks.acceptance_command(9)

    assert task("`pytest -m aceite tests/test_aceite_tarefa09.py -q`") is not None
    assert task("`pytest -m aceite tests/test_aceite_tarefa09.py -p evil.plugin`") is None
    assert task("`pytest -m aceite ../fora.py -q`") is None
    assert task("`rm -rf /`") is None


def test_run_acceptance_reports_pass_fail_and_timeout(monkeypatch):
    ok, _ = tasks.run_acceptance([sys.executable, "-c", "print('bom')"])
    assert ok is True

    ok, output = tasks.run_acceptance([sys.executable, "-c", "print('faltou X'); raise SystemExit(1)"])
    assert ok is False and "faltou X" in output

    monkeypatch.setattr(tasks, "ACCEPTANCE_TIMEOUT_SECONDS", 1)
    ok, output = tasks.run_acceptance([sys.executable, "-c", "import time; time.sleep(5)"])
    assert ok is False and "tempo limite" in output


def test_acceptance_output_is_truncated_to_protect_the_context():
    ok, output = tasks.run_acceptance([sys.executable, "-c", "print('x' * 10000); raise SystemExit(1)"])

    assert ok is False
    assert len(output) <= tasks.MAX_ACCEPTANCE_OUTPUT_CHARS + 10


# ---------------------------------------------------------
# O Harness roda o aceite (e não o juiz LLM) nas tarefas numeradas
# ---------------------------------------------------------

@pytest.fixture
def numbered(tmp_path, monkeypatch):
    tarefas = tmp_path / "tarefas"
    tarefas.mkdir()
    (tarefas / "tarefa-07-exemplo.md").write_text(
        "# Tarefa 07 — Exemplo\nQuem faz: agente\n\n## Objetivo\nFaça X.\n\n"
        "## Pronto quando\n`pytest -m aceite tests/test_aceite_tarefa07.py -q` passa.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(tasks, "TAREFAS_DIR", tarefas)
    monkeypatch.setattr(tasks, "WORKSPACE_DIR", tmp_path / "workspace")
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "saida")

    def judge_must_not_run(**kwargs):
        raise AssertionError("o juiz LLM não pode decidir uma tarefa com teste de aceite")

    monkeypatch.setattr(agent, "check_completion", judge_must_not_run)

    return tmp_path


def text_reply(text):
    return SimpleNamespace(
        message=SimpleNamespace(role="assistant", content=text, tool_calls=None),
        prompt_eval_count=100,
        eval_count=10,
    )


def test_failed_acceptance_feeds_the_output_back_and_passing_it_completes(numbered, monkeypatch):
    seen = []
    replies = iter([text_reply("concluí"), text_reply("corrigi")])
    acceptance = iter([(False, "FALTOU: arquivo ambiente.md"), (True, "ok")])

    def fake_chat(*args, **kwargs):
        seen.append(list(kwargs["messages"]))
        return next(replies)

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "run_acceptance", lambda command: next(acceptance))

    agent.agent(agent.resolve_prompt("dê continuidade à tarefa 7"))

    assert len(seen) == 2

    last = seen[1][-1]
    assert last["role"] == "user"
    assert "FALHOU" in last["content"] and "FALTOU: arquivo ambiente.md" in last["content"]
    assert "Faça X." not in last["content"], "a tarefa inteira não deve ser repetida a cada tentativa"

    log_text = logger.LOG_FILE.read_text(encoding="utf-8")
    assert "ACCEPTANCE | tentativa 1/3 | falhou" in log_text
    assert "ACCEPTANCE | tentativa 2/3 | passou" in log_text

    import json
    saved = sorted((numbered / "saida").glob("task_*.json"))[-1]
    assert json.loads(saved.read_text(encoding="utf-8"))["status"] == "completed"


def test_acceptance_that_never_passes_ends_in_needs_human(numbered, monkeypatch):
    calls = {"n": 0}

    def fake_chat(*args, **kwargs):
        calls["n"] += 1
        # Respostas diferentes: a detecção de resposta repetida não pode antecipar o limite do aceite.
        distinct = [
            "Terminei a primeira parte do trabalho.",
            "Agora corrigi o erro apontado no arquivo de formato.",
            "Revisei todos os arquivos e acho que está pronto desta vez.",
        ]
        return text_reply(distinct[(calls["n"] - 1) % len(distinct)])

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "run_acceptance", lambda command: (False, "sempre falha"))

    agent.agent(agent.resolve_prompt("dê continuidade à tarefa 7"))

    assert calls["n"] == agent.MAX_ACCEPTANCE_ATTEMPTS

    import json
    saved = sorted((numbered / "saida").glob("task_*.json"))[-1]
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["status"] == "needs_human"
    assert "teste de aceite" in data["needs_human_reason"]


# ---------------------------------------------------------
# Regravar o mesmo arquivo não é progresso
# ---------------------------------------------------------

def test_rewriting_the_same_path_stops_counting_as_progress():
    detector = StagnationDetector()
    arguments = {"path": "scripts/eval/FORMATO.md", "content": "x"}

    verdicts = [
        detector.is_progress_action("write_file", arguments, {"success": True})
        for _ in range(MAX_PROGRESS_WRITES_PER_PATH + 2)
    ]

    assert verdicts == [True] * MAX_PROGRESS_WRITES_PER_PATH + [False, False]


def test_different_paths_keep_counting_and_counts_survive_reset():
    detector = StagnationDetector()

    for _ in range(MAX_PROGRESS_WRITES_PER_PATH):
        detector.record_action("write_file", {"path": "a.md"}, {"success": True})

    assert detector.record_action("write_file", {"path": "b.md"}, {"success": True}) is True

    detector.reset()

    assert detector.record_action("write_file", {"path": "a.md"}, {"success": True}) is False


def test_repeated_rewrites_end_up_triggering_stagnation():
    detector = StagnationDetector()

    for _ in range(MAX_PROGRESS_WRITES_PER_PATH):
        detector.record_action("write_file", {"path": "a.md"}, {"success": True})

    for _ in range(detector.max_stagnation_cycles):
        detector.record_action("write_file", {"path": "a.md"}, {"success": True})

    assert detector.is_stagnated() is True


# ---------------------------------------------------------
# Registry de modelos exige o usuário
# ---------------------------------------------------------

def test_model_governance_tools_need_user_confirmation(monkeypatch):
    called = []

    def fake_tool(**kwargs):
        called.append(kwargs)
        return {"success": True}

    guarded = manager._needs_user_confirmation("set_active_smart_model", fake_tool)

    monkeypatch.setattr(manager, "CONFIRM_MODEL_GOVERNANCE", True)

    monkeypatch.setattr(manager, "request_confirmation", lambda command, reason: False)
    refused = guarded(model_name="qwen2.5:14b")

    assert refused["success"] is False and refused["cancelled"] is True
    assert called == []

    monkeypatch.setattr(manager, "request_confirmation", lambda command, reason: True)
    assert guarded(model_name="qwen2.5:14b")["success"] is True
    assert called == [{"model_name": "qwen2.5:14b"}]


def test_all_three_model_mutations_are_guarded():
    for name in ("register_model_candidate", "set_smart_candidate_for_benchmark", "set_active_smart_model"):
        assert manager.TOOLS[name].__name__ == "guarded", name

    assert manager.TOOLS["get_model_registry"].__name__ != "guarded"


# ---------------------------------------------------------
# Mensagens de erro que ajudam o modelo a se corrigir
# ---------------------------------------------------------

def test_unterminated_string_error_explains_the_newline_mistake(tmp_path):
    from core.paths import TMP_ROOT

    target = TMP_ROOT / "localagent_hint_test.py"
    target.unlink(missing_ok=True)

    broken = 'texto = "linha 1\nlinha 2"\n'

    result = write_file(str(target), broken)

    assert result["success"] is False
    assert "Dica" in result["error"] and "\\n" in result["error"]
    assert "Linha:" in result["error"]
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="dica específica do Windows")
def test_unix_command_not_found_on_windows_points_to_the_right_tools(monkeypatch):
    import tools.terminal as terminal

    def not_found(*args, **kwargs):
        raise FileNotFoundError("[WinError 2] O sistema não pode encontrar o arquivo especificado")

    monkeypatch.setattr(terminal.subprocess, "run", not_found)

    result = terminal.run_command("cat tests/x.py", "Ler o arquivo")

    assert result["success"] is False
    assert "read_file" in result["error"] and "search_files" in result["error"]


# ---------------------------------------------------------
# Calibração e conteúdo das tarefas
# ---------------------------------------------------------

def test_token_estimate_is_calibrated_to_the_real_log():
    assert estimate_tokens("x" * 360) == 100


def test_task_02_uses_fixed_file_names_so_reruns_do_not_duplicate_ids():
    text = next((PROJECT_ROOT / "tarefas").glob("tarefa-02-*.md")).read_text(encoding="utf-8")

    for index in range(1, 6):
        assert f"scripts/eval/tarefas/tarefa-0{index}.json" in text

    assert "sobrescreva" in text.lower()
    assert len(text) < 3500


def test_task_03_warns_about_string_newlines_and_about_creating_files():
    text = next((PROJECT_ROOT / "tarefas").glob("tarefa-03-*.md")).read_text(encoding="utf-8")

    assert "write_file" in text and "aspas triplas" in text
