from types import SimpleNamespace

import agent


def _role(message):
    return message["role"] if isinstance(message, dict) else message.role


def _tool_calls(message):
    if isinstance(message, dict):
        return message.get("tool_calls") or []
    return getattr(message, "tool_calls", None) or []


def _assert_every_tool_call_has_a_response(messages):
    index = 0
    while index < len(messages):
        message = messages[index]
        calls = _tool_calls(message)

        if _role(message) == "assistant" and calls:
            following = []
            cursor = index + 1
            while cursor < len(messages) and _role(messages[cursor]) == "tool":
                following.append(messages[cursor])
                cursor += 1
            assert len(following) == len(calls), (
                f"{len(calls)} tool_calls mas {len(following)} respostas"
            )
            index = cursor
            continue

        index += 1


def test_interrupted_tool_batch_still_answers_every_tool_call(tmp_path, monkeypatch):
    def response_with_four_calls():
        calls = [
            SimpleNamespace(function=SimpleNamespace(name="get_project_status", arguments={}))
            for _ in range(4)
        ]
        message = SimpleNamespace(role="assistant", content="", tool_calls=calls)
        return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)

    seen = []

    def fake_chat(*args, **kwargs):
        seen.append(list(kwargs["messages"]))
        return response_with_four_calls()

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(
        agent.ModelRouter,
        "check_smart_availability",
        lambda self, *a, **k: (True, "smart disponível (teste)", {}),
    )
    monkeypatch.setattr(agent.ModelRouter, "get_smart_model", lambda self: "smart-model")
    monkeypatch.setattr(agent, "MAX_ITERATIONS", 6)

    agent.agent("Tarefa de teste de consistência do loop")

    assert len(seen) >= 2, "o modelo precisa ser chamado de novo após a interrupção"

    for messages in seen:
        _assert_every_tool_call_has_a_response(messages)
