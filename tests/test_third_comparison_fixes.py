"""Correções a partir da comparação de 09/10/2026 (logs/comparacao/20261009_200900)."""

import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent  # noqa: E402
import comparar_modelos as cmp  # noqa: E402
from core.harness.completion import build_continuation_reason, check_completion  # noqa: E402
from core.paths import PROJECT_ROOT, WORKSPACE_DIR  # noqa: E402
from tools import terminal  # noqa: E402


def registry_with_smart_candidate(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({
        "active_smart_model": None,
        "models": {"candidato:12b": {"role": "smart", "status": "candidate"}},
    }), encoding="utf-8")
    return path


def tool_call_response(name, arguments):
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))
    message = SimpleNamespace(role="assistant", content="", tool_calls=[call])
    return SimpleNamespace(message=message, prompt_eval_count=1, eval_count=1)


def capture_log(monkeypatch):
    events = []
    monkeypatch.setattr(agent, "log", lambda event, text="": events.append((event, str(text))))
    return events


# ---------------------------------------------------------
# A fase do projeto não invade tarefas avulsas
# ---------------------------------------------------------

def test_a_standalone_task_does_not_get_the_smart_selection_guidance(tmp_path):
    registry = registry_with_smart_candidate(tmp_path)

    plain = build_continuation_reason(base_reason="falta rodar o programa", registry_path=registry, include_guidance=False)
    dev = build_continuation_reason(base_reason="falta rodar o programa", registry_path=registry)

    assert "set_smart_candidate_for_benchmark" not in plain and plain == "falta rodar o programa"
    assert "set_smart_candidate_for_benchmark" in dev


def test_check_completion_after_a_failed_tool_respects_include_guidance(tmp_path):
    registry = registry_with_smart_candidate(tmp_path)

    result = check_completion(
        model="m", task="Crie resumo.py", response="feito", tool_calls=1, successful_tools=0, failed_tools=1,
        last_tool_success=False, last_failure_reason="erro", registry_path=registry, include_guidance=False,
    )

    assert result["status"] == "continue" and "PRÓXIMA TRANSIÇÃO" not in result["reason"]


def test_the_agent_keeps_project_guidance_out_of_a_standalone_task(tmp_path, monkeypatch):
    sent = []
    responses = iter([
        tool_call_response("read_file", {"path": "workspace/nao-existe-1.txt"}),
        SimpleNamespace(message=SimpleNamespace(role="assistant", content="Terminei.", tool_calls=None), prompt_eval_count=1, eval_count=1),
    ])

    def fake_chat(*args, **kwargs):
        sent.append([m["content"] if isinstance(m, dict) else m.content for m in kwargs["messages"]])
        try:
            return next(responses)
        except StopIteration:
            raise RuntimeError("fim do teste")

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr("core.harness.completion.REGISTRY_PATH", registry_with_smart_candidate(tmp_path))
    capture_log(monkeypatch)

    agent.agent("Crie workspace/bateria/resumo.py que imprime oi")

    # O que o Harness acrescentou depois do pedido (o system prompt só lista os nomes das ferramentas).
    later = "\n".join(str(c) for c in sent[-1][2:])
    assert "A tarefa ainda não foi concluída" in later
    assert "set_smart_candidate_for_benchmark" not in later
    assert "update_spec_checklist" not in later


# ---------------------------------------------------------
# 'cd PASTA && comando'
# ---------------------------------------------------------

def test_leading_cd_into_workspace_is_split_into_folder_and_command():
    folder, rest, error = terminal._split_leading_cd('cd "workspace" && python x.py')

    assert error is None and folder == WORKSPACE_DIR.resolve() and rest == "python x.py"


def test_leading_cd_accepts_a_slash_prefixed_project_path():
    folder, rest, error = terminal._split_leading_cd("cd /workspace && python -m pytest -q")

    assert error is None and folder == WORKSPACE_DIR.resolve() and rest == "python -m pytest -q"


def test_leading_cd_outside_workspace_is_refused():
    for command in ("cd core && del paths.py", "cd .. && dir", "cd C:\\Windows && dir"):
        folder, _, error = terminal._split_leading_cd(command)
        assert folder is None and "workspace/" in error, command


def test_commands_without_cd_are_untouched():
    assert terminal._split_leading_cd("python x.py") == (None, "python x.py", None)
    assert terminal._split_leading_cd("echo a && echo b") == (None, "echo a && echo b", None)


def test_run_command_runs_in_the_cd_folder(tmp_path, monkeypatch):
    target = WORKSPACE_DIR / "teste-cd-tmp"
    target.mkdir(parents=True, exist_ok=True)
    (target / "onde.py").write_text("import os; print(os.path.basename(os.getcwd()))", encoding="utf-8")
    shown = []
    monkeypatch.setattr(terminal, "authorize", lambda command, reason: shown.append((command, reason)) or True)

    try:
        result = terminal.run_command(f"cd {target} && {sys.executable} onde.py", "ver a pasta")
    finally:
        for item in target.iterdir():
            item.unlink()
        target.rmdir()

    assert result["success"] and result["stdout"].strip() == "teste-cd-tmp"
    assert "&&" not in shown[0][0] and "workspace/teste-cd-tmp" in shown[0][1]


# ---------------------------------------------------------
# Chamada de ferramenta malformada
# ---------------------------------------------------------

def test_malformed_tool_call_errors_are_recognised():
    assert agent.is_malformed_tool_call(Exception("error parsing tool call: raw='{...}' (status code: 500)"))
    assert agent.is_malformed_tool_call(Exception("XML syntax error on line 13: element <function> closed by </parameter>"))
    assert not agent.is_malformed_tool_call(Exception("connection refused"))


def test_a_malformed_tool_call_gets_a_hint_and_a_new_try_before_failing(tmp_path, monkeypatch):
    sent = []

    def fake_chat(*args, **kwargs):
        sent.append(kwargs["messages"][-1])
        raise RuntimeError("error parsing tool call: raw='{\"a\":\"b\"+x}' (status code: 500)")

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    events = capture_log(monkeypatch)

    agent.agent("Crie workspace/bateria/x.py")

    assert len(sent) == agent.MAX_MALFORMED_TOOL_CALLS + 1
    assert sent[1]["content"] == agent.MALFORMED_TOOL_CALL_HINT
    assert [e for e, _ in events].count("MALFORMED_TOOL_CALL") == agent.MAX_MALFORMED_TOOL_CALLS
    assert any(e == "STOP" for e, _ in events)


# ---------------------------------------------------------
# SMART indisponível: o FAST ganha uma segunda chance
# ---------------------------------------------------------

def test_without_smart_the_fast_retries_once_after_tool_errors(tmp_path, monkeypatch):
    counter = {"n": 0}

    def fake_chat(*args, **kwargs):
        counter["n"] += 1
        return tool_call_response("read_file", {"path": f"workspace/nao-existe-{counter['n']}.txt"})

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(
        agent.ModelRouter, "check_smart_availability",
        lambda self, *a, **k: (False, "sem SMART (teste)", {"event": "SMART_UNAVAILABLE"}),
    )
    events = capture_log(monkeypatch)

    agent.agent("Leia os arquivos de workspace/bateria e some os números")

    names = [e for e, _ in events]
    assert names.count("FAST_RETRY") == 1
    assert names.count("ESCALATE_TO_SMART") == 2
    assert names.index("FAST_RETRY") < len(names) - 1 and names[-1] != "FAST_RETRY"


# ---------------------------------------------------------
# Comparativo: modelo que não carrega ganha uma segunda tentativa
# ---------------------------------------------------------

def args():
    return SimpleNamespace(modelos="", perfis="", repeticoes=1, rapido=False, limite_modelo=5)


def test_a_model_that_fails_to_load_once_is_retried_and_its_first_log_is_kept(tmp_path, monkeypatch):
    smokes = iter([
        {"ok": False, "tool_call": False, "seconds": 1, "error": "llama-server process has terminated: exit status 0xc0000409"},
        {"ok": True, "tool_call": True, "seconds": 1, "error": ""},
    ])
    ran = []

    @contextlib.contextmanager
    def fake_server(profile, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "servidor-ollama.log").write_text("CUDA error", encoding="utf-8")
        yield "http://127.0.0.1:11435"

    monkeypatch.setattr(cmp, "model_installed", lambda m: True)
    monkeypatch.setattr(cmp, "server_for", fake_server)
    monkeypatch.setattr(cmp, "smoke_test", lambda *a, **k: next(smokes))
    monkeypatch.setattr(cmp, "free_gpu", lambda: ran.append("free"))
    monkeypatch.setattr(cmp, "SMOKE_RETRY_WAIT_SECONDS", 0)
    monkeypatch.setattr(cmp, "run_one", lambda profile, folder, a, resume=False, url=None: ran.append("bateria"))
    monkeypatch.setattr(cmp, "collect", lambda folder, label: {"label": label, "results": [], "meta": {}})
    entries: list[dict] = []
    profile = {"label": "s-gemma12", "model": "gemma4:12b", "num_ctx": 8192, "server": cmp.KV8}

    cmp.run_model(profile, tmp_path, args(), entries, False, lambda: True)

    assert ran == ["free", "bateria"]
    assert "skipped" not in entries[0]
    assert (tmp_path / "s-gemma12" / "servidor-ollama-falha-1.log").read_text(encoding="utf-8") == "CUDA error"


def test_a_model_that_never_loads_is_skipped_after_the_retries(tmp_path, monkeypatch):
    @contextlib.contextmanager
    def fake_server(profile, folder):
        yield "http://127.0.0.1:11435"

    monkeypatch.setattr(cmp, "model_installed", lambda m: True)
    monkeypatch.setattr(cmp, "server_for", fake_server)
    monkeypatch.setattr(cmp, "smoke_test", lambda *a, **k: {"ok": False, "tool_call": False, "seconds": 1, "error": "quebrou"})
    monkeypatch.setattr(cmp, "free_gpu", lambda: None)
    monkeypatch.setattr(cmp, "SMOKE_RETRY_WAIT_SECONDS", 0)
    entries: list[dict] = []

    cmp.run_model({"label": "x", "model": "m", "num_ctx": 8192}, tmp_path, args(), entries, False, lambda: True)

    assert entries[0]["skipped"] == "incompatível: quebrou"


def test_loaded_models_reads_the_names_from_ollama_ps(monkeypatch):
    listing = "NAME          ID    SIZE\nqwen3.5:9b    abc   5.6 GB\ngemma4:12b    def   8 GB\n"
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60, env=None: (0, listing))

    assert cmp.loaded_models() == ["qwen3.5:9b", "gemma4:12b"]


# ---------------------------------------------------------
# Decisão do FAST e configuração do servidor
# ---------------------------------------------------------

def test_the_fast_decision_is_recorded_with_the_server_settings_it_needs():
    registry = json.loads((PROJECT_ROOT / "models" / "registry.json").read_text(encoding="utf-8"))
    fast = registry["models"]["qwen3.5:9b"]

    assert registry["active_fast_model"] == "qwen3.5:9b" and fast["status"] == "adopted"
    assert fast["server_env"] == cmp.KV8
    assert "20261009_200900" in fast["justification"]
    assert registry["active_smart_model"] is None, "o SMART ainda não foi decidido"


def test_the_installer_applies_the_server_settings_of_the_active_model_and_restarts_ollama():
    script = (PROJECT_ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")

    assert "server_env" in script and "SetEnvironmentVariable" in script
    assert "Stop-Process" in script and "ollama app.exe" in script


def test_the_next_run_confirms_the_fast_and_measures_the_smart_candidates():
    assert cmp.FAST_PROFILES == ["9b-kv8", "9b-16k-kv8"]
    assert {"s-gemma12", "s-gptoss20", "par-9b+gemma12", "par-9b+gptoss20"} <= set(cmp.SMART_PROFILES)
    assert cmp.PROFILES["par-9b+gptoss20"]["smart_model"] == "gpt-oss:20b"


def test_the_evaluation_table_uses_the_profile_name_even_when_meta_only_has_the_model(tmp_path):
    import registrar_avaliacoes as reg

    night = tmp_path / "noite"
    for label, model in (("9b-kv8", "qwen3.5:9b"), ("9b-think", "qwen3.5:9b"), ("s-gptoss20", "gpt-oss:20b"), ("par-9b+gemma12", "qwen3.5:9b")):
        folder = night / cmp.slug(label)
        folder.mkdir(parents=True)
        (folder / "resultados.json").write_text(json.dumps([{"id": "a", "passed": True, "group": "real", "seconds": 1.0, "tools": 1,
            "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "tok_s": 50.0, "detail": ""}]), encoding="utf-8")
        (folder / "meta.json").write_text(json.dumps({"model": model}), encoding="utf-8")
    output = tmp_path / "avaliacoes.md"

    reg.main([str(night), "--saida", str(output)])
    text = output.read_text(encoding="utf-8")

    assert "| FAST sozinho | 9b-kv8 |" in text and "| FAST com think | 9b-think |" in text
    assert "| SMART sozinho | s-gptoss20 |" in text and "| Cascata (FAST + SMART) | par-9b+gemma12 |" in text
