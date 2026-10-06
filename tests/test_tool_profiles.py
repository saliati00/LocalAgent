import json
from types import SimpleNamespace

import pytest

import agent
import core.tasks as tasks
from core.context.metrics import estimate_tokens


def names(tools):
    return [t["function"]["name"] for t in tools]


# ---------------------------------------------------------
# Estrutura dos grupos
# ---------------------------------------------------------

def test_every_tool_belongs_to_exactly_one_group():
    grouped = [name for group in agent.TOOL_GROUPS.values() for name in group]

    assert sorted(grouped) == sorted(t["function"]["name"] for t in agent.TOOLS)
    assert len(grouped) == len(set(grouped))


def test_base_group_is_small_and_has_the_essentials():
    base = agent.TOOL_GROUPS["base"]

    assert len(base) <= 8
    for essential in ("read_file", "write_file", "replace_in_file", "run_command", "search_files"):
        assert essential in base


# ---------------------------------------------------------
# Seleção por tarefa
# ---------------------------------------------------------

def test_plain_task_gets_only_the_base_group():
    assert agent.select_tool_groups("Liste os arquivos da pasta workspace") == {"base"}


@pytest.mark.parametrize("prompt, group", [
    ("Pesquise na internet a versão do llama.cpp", "web"),
    ("Baixe o arquivo https://exemplo.com/a.zip", "web"),
    ("Salve na memória que o git está instalado", "memory"),
    ("Registre o candidato no registry", "models"),
    ("Atualize o checklist", "project"),
])
def test_keywords_enable_extra_groups(prompt, group):
    assert group in agent.select_tool_groups(prompt)


def test_development_flow_adds_project_and_memory_and_models_only_for_model_phases():
    groups = agent.select_tool_groups("Continue o desenvolvimento", is_dev_task=True, phase_text="FASE 11 criar avaliação")
    assert {"project", "memory"} <= groups and "models" not in groups

    groups = agent.select_tool_groups("Continue", is_dev_task=True, phase_text="FASE 2 — SMART Baixar modelo")
    assert "models" in groups


def test_numbered_task_01_needs_only_the_base_tools(monkeypatch):
    ok, prompt = tasks.build_task_prompt(1, "dê continuidade à tarefa 1")

    assert ok is True
    assert agent.select_tool_groups(prompt) == {"base"}


# ---------------------------------------------------------
# Schema visível
# ---------------------------------------------------------

def test_visible_tools_follow_group_order_and_hide_propose_skill_from_fast():
    base_only = names(agent.visible_tools(False, {"base"}))
    assert base_only == agent.TOOL_GROUPS["base"]

    with_web = names(agent.visible_tools(False, {"base", "web"}))
    assert with_web == agent.TOOL_GROUPS["base"] + agent.TOOL_GROUPS["web"]

    assert "propose_skill" not in names(agent.visible_tools(False))
    assert "propose_skill" in names(agent.visible_tools(True, {"base"}))
    assert "web_search" not in names(agent.visible_tools(True, {"base"}))


def test_default_visible_tools_still_expose_everything_for_smart():
    assert set(names(agent.visible_tools(True))) == {t["function"]["name"] for t in agent.TOOLS}


def test_base_schema_fits_a_small_budget():
    chars = len(json.dumps(agent.visible_tools(False, {"base"}), ensure_ascii=False))

    assert estimate_tokens("x" * chars) < 1600, f"schema base com {chars} caracteres"


# ---------------------------------------------------------
# No loop do agente
# ---------------------------------------------------------

def test_calling_a_hidden_tool_enables_its_group_for_the_next_turn(tmp_path, monkeypatch):
    from core.harness import logger

    seen = []

    def response(call):
        return SimpleNamespace(
            message=SimpleNamespace(role="assistant", content="", tool_calls=[call] if call else None),
            prompt_eval_count=100,
            eval_count=5,
        )

    scripted = iter([
        response(SimpleNamespace(function=SimpleNamespace(name="get_memory", arguments={"category": "notes"}))),
        SimpleNamespace(
            message=SimpleNamespace(role="assistant", content="pronto", tool_calls=None),
            prompt_eval_count=100,
            eval_count=5,
        ),
    ])

    def fake_chat(*args, **kwargs):
        seen.append(set(names(kwargs["tools"])))
        return next(scripted)

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "check_completion", lambda **kw: {"status": "complete", "reason": "ok"})

    agent.agent("Liste os arquivos da pasta workspace")

    assert "get_memory" not in seen[0]
    assert "get_memory" in seen[1]
    assert "TOOL_GROUP_ENABLED" in logger.LOG_FILE.read_text(encoding="utf-8")


def test_system_prompt_lists_the_hidden_tools_by_name(tmp_path, monkeypatch):
    captured = {}

    def fake_chat(*args, **kwargs):
        captured["system"] = kwargs["messages"][0]["content"]
        return SimpleNamespace(
            message=SimpleNamespace(role="assistant", content="ok", tool_calls=None),
            prompt_eval_count=10,
            eval_count=5,
        )

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "check_completion", lambda **kw: {"status": "complete", "reason": "ok"})

    agent.agent("Liste os arquivos da pasta workspace")

    assert "Outras ferramentas" in captured["system"]
    assert "web_search" in captured["system"] and "get_model_registry" in captured["system"]
    assert "propose_skill" not in captured["system"]
