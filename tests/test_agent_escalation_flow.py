import json
from types import SimpleNamespace

import agent
from core.harness import logger


def tool_call_response(name="get_project_status", arguments=None):
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments or {}))
    message = SimpleNamespace(role="assistant", content="", tool_calls=[call])
    return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)


def text_response(text):
    message = SimpleNamespace(role="assistant", content=text, tool_calls=None)
    return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)


def saved_task(tmp_path):
    files = sorted((tmp_path / "tasks").glob("task_*.json"))
    assert files, "o estado da tarefa deveria ter sido salvo"
    return json.loads(files[-1].read_text(encoding="utf-8"))


def make_smart_available(monkeypatch):
    monkeypatch.setattr(
        agent.ModelRouter,
        "check_smart_availability",
        lambda self, *a, **k: (True, "smart disponível (teste)", {"active_smart_model": "smart-model"}),
    )
    monkeypatch.setattr(agent.ModelRouter, "get_smart_model", lambda self: "smart-model")


def test_escalation_hands_over_a_short_packet_and_returns_to_fast(tmp_path, monkeypatch):
    calls = []

    def fake_chat(*args, **kwargs):
        messages = list(kwargs["messages"])
        calls.append((kwargs["model"], messages))
        return tool_call_response()

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "MAX_ITERATIONS", 80)
    monkeypatch.setattr(agent, "SMART_MAX_ITERATIONS", 2)
    monkeypatch.setattr(agent, "MAX_ESCALATIONS", 2)
    make_smart_available(monkeypatch)

    agent.agent("Tarefa de teste de passagem entre modelos")

    models = [model for model, _ in calls]

    assert models[0] != "smart-model"
    assert "smart-model" in models
    first_smart = models.index("smart-model")

    # O SMART começa de um pacote curto, não do histórico do FAST.
    smart_messages = calls[first_smart][1]
    assert len(smart_messages) == 2
    assert "PASSAGEM DE TAREFA" in smart_messages[1]["content"]

    # Depois de usar suas iterações, a tarefa volta ao FAST.
    assert any(m != "smart-model" for m in models[first_smart:])

    # Escaladas sem fim viram NEEDS_HUMAN (e não um loop infinito).
    task = saved_task(tmp_path)
    assert task["status"] == "needs_human"
    assert "escalada" in task["needs_human_reason"]


def test_repeated_text_response_stops_with_needs_human(tmp_path, monkeypatch):
    count = {"n": 0}

    def fake_chat(*args, **kwargs):
        count["n"] += 1
        return text_response("Preciso da senha de administrador. Execute o comando manualmente.")

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(
        agent,
        "check_completion",
        lambda **kwargs: {"status": "continue", "reason": "ainda não concluída"},
    )

    agent.agent("Instale o git com sudo")

    assert count["n"] == 3

    task = saved_task(tmp_path)
    assert task["status"] == "needs_human"
    assert task["needs_human_reason"]


def test_repeated_read_only_tool_is_served_from_cache(tmp_path, monkeypatch):
    responses = iter([
        tool_call_response("get_model_registry", {}),
        tool_call_response("get_model_registry", {}),
        text_response("Consultei o registry."),
    ])

    monkeypatch.setattr(agent.client, "chat", lambda *a, **k: next(responses))
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(
        agent,
        "check_completion",
        lambda **kwargs: {"status": "complete", "reason": "ok"},
    )

    agent.agent("Liste os modelos do registry")

    log_text = logger.LOG_FILE.read_text(encoding="utf-8")

    assert log_text.count("TOOL_CACHE_HIT") == 1
    assert saved_task(tmp_path)["status"] == "completed"
