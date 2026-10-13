"""Modo só FAST e a ponte da interface web (Open WebUI)."""

import json
import sys
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent  # noqa: E402
import iniciar_web  # noqa: E402
import ponte_web  # noqa: E402
from core.harness import permissions  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402


def log_line(event, details=""):
    return f"[2026-10-13 09:00:00] [abcd1234] {event}" + (f" | {details}" if details else "")


# ---------------------------------------------------------
# Gancho de confirmação
# ---------------------------------------------------------

def test_the_confirmation_hook_replaces_the_terminal_question(monkeypatch):
    monkeypatch.setattr(permissions, "CONFIRMATION_HANDLER", lambda command, reason: command == "python x.py")
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("não devia perguntar no terminal"))

    assert permissions.request_confirmation("python x.py", "rodar") is True
    assert permissions.request_confirmation("del y", "apagar") is False


def test_without_the_hook_the_terminal_is_still_used(monkeypatch):
    monkeypatch.setattr(permissions, "CONFIRMATION_HANDLER", None)
    monkeypatch.setattr("builtins.input", lambda *a: "")

    assert permissions.request_confirmation("python x.py", "rodar") is True


# ---------------------------------------------------------
# Modo só FAST
# ---------------------------------------------------------

def tool_call_response(name, arguments):
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))
    message = SimpleNamespace(role="assistant", content="", tool_calls=[call])
    return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)


def text_response(text):
    message = SimpleNamespace(role="assistant", content=text, tool_calls=None)
    return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)


def capture_log(monkeypatch):
    events = []
    monkeypatch.setattr(agent, "log", lambda event, text="": events.append((event, str(text))))
    return events


def test_fast_only_never_asks_for_the_smart_and_stops_with_an_explanation(tmp_path, monkeypatch):
    counter = {"n": 0}

    def fake_chat(*args, **kwargs):
        counter["n"] += 1
        return tool_call_response("read_file", {"path": f"workspace/nao-existe-{counter['n']}.txt"})

    monkeypatch.setattr(agent, "SO_FAST", True)
    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent.ModelRouter, "check_smart_availability", lambda self, *a, **k: pytest.fail("não devia procurar o SMART"))
    events = capture_log(monkeypatch)

    result = agent.agent("Leia os arquivos de workspace/bateria e some os números")
    names = [e for e, _ in events]

    assert names.count("ESCALATION_SKIPPED") == 2 and "ESCALATE_TO_SMART" not in names
    assert names.count("NEEDS_HUMAN") == 1
    assert result["status"] == "needs_human"
    assert counter["n"] < 20


def test_the_default_mode_still_escalates(tmp_path, monkeypatch):
    counter = {"n": 0}

    def fake_chat(*args, **kwargs):
        counter["n"] += 1
        return tool_call_response("read_file", {"path": f"workspace/nao-existe-{counter['n']}.txt"})

    monkeypatch.setattr(agent, "SO_FAST", False)
    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent.ModelRouter, "check_smart_availability", lambda self, *a, **k: (False, "sem SMART", {"event": "SMART_UNAVAILABLE"}))
    events = capture_log(monkeypatch)

    agent.agent("Leia os arquivos de workspace/bateria e some os números")

    assert [e for e, _ in events].count("ESCALATE_TO_SMART") >= 1
    assert "ESCALATION_SKIPPED" not in [e for e, _ in events]


def test_the_flag_comes_from_the_environment():
    source = (PROJECT_ROOT / "agent.py").read_text(encoding="utf-8")

    assert 'os.environ.get("LOCALAGENT_SO_FAST"' in source


def test_agent_returns_the_final_response_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr(agent.client, "chat", lambda *a, **k: text_response("Feito: criei o arquivo."))
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "check_completion", lambda **k: {"status": "complete", "reason": "ok"})
    capture_log(monkeypatch)

    result = agent.agent("Diga oi")

    assert result == {"status": "completed", "response": "Feito: criei o arquivo."}


# ---------------------------------------------------------
# Ponte: pedaços
# ---------------------------------------------------------

def test_progress_lines_show_tools_and_results_and_ignore_the_rest():
    assert ponte_web.progress_line("TOOL", "list_directory | {'path': 'workspace'}").startswith("🔧 `list_directory`")
    assert ponte_web.progress_line("RESULT", "list_directory | OK") == "   ✓ ok"
    assert "arquivo não encontrado" in ponte_web.progress_line("RESULT", "read_file | FAIL | arquivo não encontrado")
    assert ponte_web.progress_line("TOKENS", "input=1") is None


def test_the_line_writer_keeps_only_harness_log_lines():
    got = []
    writer = ponte_web.LineWriter(got.append)

    writer.write("texto solto\n" + log_line("TOOL", "read_file | {}") + "\n" + log_line("ITERATION", "1/30") + "\n")
    writer.write(log_line("RESULT", "read_file | OK")[:20])
    writer.write(log_line("RESULT", "read_file | OK")[20:] + "\n")

    assert len(got) == 2 and got[0].startswith("🔧 `read_file`") and got[1] == "   ✓ ok"


def test_the_final_text_adds_a_note_when_the_task_did_not_finish():
    assert ponte_web.final_text({"status": "completed", "response": "Pronto."}) == "Pronto."
    assert "Preciso de você" in ponte_web.final_text({"status": "needs_human", "response": "Falta a senha."})
    assert "não terminou" in ponte_web.final_text({"status": "failed", "response": ""})


# ---------------------------------------------------------
# Ponte: servidor de verdade (porta livre), agente de mentira
# ---------------------------------------------------------

@pytest.fixture
def bridge():
    calls = []

    def fake_agent(prompt):
        calls.append(prompt)
        print(log_line("TOOL", "list_directory | {'path': 'workspace'}"))
        print(log_line("RESULT", "list_directory | OK"))

        if "confirme" in prompt:
            allowed = permissions.request_confirmation("python x.py", "Verificar o programa")
            return {"status": "completed", "response": "executou" if allowed else "cancelou"}

        return {"status": "completed", "response": "Tudo certo."}

    server, session = ponte_web.build_server(0, run_agent=fake_agent, resolve_prompt=lambda text: text)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    yield SimpleNamespace(base=base, calls=calls, session=session)

    server.shutdown()
    server.server_close()


def post(base, text, stream=False):
    body = json.dumps({"model": "localagent", "stream": stream, "messages": [{"role": "user", "content": text}]}).encode("utf-8")
    request = urllib.request.Request(base + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def reply_text(raw):
    return json.loads(raw)["choices"][0]["message"]["content"]


def test_the_bridge_lists_one_model(bridge):
    with urllib.request.urlopen(bridge.base + "/v1/models", timeout=10) as response:
        data = json.loads(response.read())

    assert [m["id"] for m in data["data"]] == ["localagent"]


def test_a_chat_request_runs_the_agent_and_returns_progress_and_the_answer(bridge):
    text = reply_text(post(bridge.base, "liste a pasta"))

    assert bridge.calls == ["liste a pasta"]
    assert "🔧 `list_directory`" in text and "✓ ok" in text and "Tudo certo." in text


def test_the_stream_follows_the_openai_format_and_ends_with_done(bridge):
    raw = post(bridge.base, "liste a pasta", stream=True)
    events = [line[6:] for line in raw.splitlines() if line.startswith("data: ")]

    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert "Tudo certo." in "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)


@pytest.mark.parametrize("answer, expected", [("sim", "executou"), ("NÃO", "cancelou")])
def test_a_confirmation_becomes_a_question_in_the_chat_and_the_next_message_answers_it(bridge, answer, expected):
    first = reply_text(post(bridge.base, "confirme o programa"))

    assert "Responda **SIM**" in first and "python x.py" in first and expected not in first
    assert bridge.session.waiting

    second = reply_text(post(bridge.base, answer))

    assert expected in second and bridge.calls == ["confirme o programa"], "a resposta não pode virar uma tarefa nova"


def test_the_assistant_s_automatic_requests_do_not_run_the_agent(bridge):
    text = reply_text(post(bridge.base, "### Task:\nGenerate a concise title for this chat"))

    assert text == "LocalAgent" and bridge.calls == []


def test_a_new_task_while_another_runs_is_refused_politely(bridge):
    release = threading.Event()
    bridge.session.run_agent = lambda prompt: release.wait(10) and {"status": "completed", "response": "x"}
    bridge.session.start("tarefa demorada")

    try:
        text = reply_text(post(bridge.base, "outra tarefa"))
    finally:
        release.set()

    assert "tarefa em andamento" in text


def test_the_confirmation_hook_is_removed_when_the_task_ends(bridge):
    post(bridge.base, "liste a pasta")

    assert permissions.CONFIRMATION_HANDLER is None


# ---------------------------------------------------------
# Inicialização, instalador e limpeza
# ---------------------------------------------------------

def test_open_webui_is_configured_to_use_only_the_bridge_and_keep_data_inside_the_project():
    env = iniciar_web.webui_environment(8765)

    assert env["OPENAI_API_BASE_URL"] == "http://127.0.0.1:8765/v1" and env["ENABLE_OLLAMA_API"] == "False"
    assert Path(env["DATA_DIR"]).resolve().parent == PROJECT_ROOT.resolve()
    assert env["ENABLE_TITLE_GENERATION"] == "False" and env["ENABLE_TAGS_GENERATION"] == "False"
    assert iniciar_web.webui_executable().resolve().is_relative_to(PROJECT_ROOT.resolve())


def test_everything_the_web_interface_installs_stays_inside_the_project_and_out_of_git():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")

    assert ".venv-webui/" in ignored and "data-webui/" in ignored
    assert "open-webui" in script and ".venv-webui" in script and "SkipWeb" in script
    assert "3.12" in script and "3.11" in script, "o Open WebUI só funciona nesses Pythons"


def test_the_launchers_exist_and_set_up_what_they_need():
    fast = (PROJECT_ROOT / "iniciar-fast.bat").read_text(encoding="utf-8")
    web = (PROJECT_ROOT / "iniciar-web.bat").read_text(encoding="utf-8")

    assert "LOCALAGENT_SO_FAST=1" in fast and "agent.py" in fast
    assert "iniciar_web.py" in web and ".venv-webui" in web


@pytest.mark.parametrize("relative", ["iniciar-fast.bat", "iniciar-web.bat", "scripts/ponte_web.py", "scripts/iniciar_web.py"])
def test_the_new_launchers_and_bridge_are_protected_from_the_agent(relative):
    from tools.filesystem import PROTECTED_PATHS, write_file

    assert (PROJECT_ROOT / relative).resolve() in PROTECTED_PATHS
    assert write_file(str(PROJECT_ROOT / relative), "x")["success"] is False
