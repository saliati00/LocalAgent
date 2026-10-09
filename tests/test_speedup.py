"""Aceleração: bateria enxuta, perfil com raciocínio ligado, registro das avaliações e itens já feitos marcados."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent  # noqa: E402
import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402
import registrar_avaliacoes as reg  # noqa: E402
from core.paths import PROJECT_SPEC_PATH  # noqa: E402


def test_simple_cases_run_once_and_the_discriminating_groups_twice():
    by_group = {}

    for case in bateria.CASES:
        by_group.setdefault(case["group"], set()).add(case["repeat"])

    assert by_group["simples"] == {1}
    assert by_group["raciocinio"] == {2} and by_group["real"] == {2}


def test_default_profiles_drop_what_was_already_decided_and_add_think():
    assert "8b" not in cmp.DEFAULT_PROFILES and "s-coder30" not in cmp.DEFAULT_PROFILES
    assert "9b-think" in cmp.FAST_PROFILES
    assert cmp.PROFILES["9b-think"]["think"] is True


def test_think_profile_exports_the_flag_and_a_longer_call_timeout(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cmp, "run_guarded", lambda command, env, cwd, timeout, **k: seen.update(env=env) or "ok")
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: None)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)

    cmp.run_one({"label": "9b-think", **cmp.PROFILES["9b-think"]}, tmp_path, SimpleNamespace(repeticoes=2, rapido=False, limite_modelo=5))

    assert seen["env"]["LOCALAGENT_THINK"] == "1" and seen["env"]["LOCALAGENT_CALL_TIMEOUT"] == "300"


def test_profiles_without_think_do_not_turn_it_on(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cmp, "run_guarded", lambda command, env, cwd, timeout, **k: seen.update(env=env) or "ok")
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: None)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)
    monkeypatch.delenv("LOCALAGENT_THINK", raising=False)

    cmp.run_one({"label": "9b", **cmp.PROFILES["9b"]}, tmp_path, SimpleNamespace(repeticoes=2, rapido=False, limite_modelo=5))

    assert "LOCALAGENT_THINK" not in seen["env"]


def test_the_smoke_test_uses_the_profile_think_setting(monkeypatch):
    import ollama

    seen = {}

    class Client:
        def __init__(self, *a, **k):
            pass

        def chat(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(message=SimpleNamespace(tool_calls=[1]))

    monkeypatch.setattr(ollama, "Client", Client)
    cmp.smoke_test("qwen3.5:9b", think=True)

    assert seen["think"] is True


def test_the_agent_reads_think_from_the_environment(monkeypatch):
    import importlib

    monkeypatch.setenv("LOCALAGENT_THINK", "1")
    assert importlib.reload(agent).THINK is True

    monkeypatch.delenv("LOCALAGENT_THINK")
    assert importlib.reload(agent).THINK is False


# ---------------------------------------------------------
# specs/avaliacoes.md
# ---------------------------------------------------------

def result(case_id, group, passed, info=False):
    return {"id": case_id, "passed": passed, "group": group, "info": info, "tok_s": 50.0, "seconds": 1.0, "tools": 1,
            "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}


def profile_folder(base, label, results, meta=None):
    folder = base / cmp.slug(label)
    folder.mkdir(parents=True)
    (folder / "resultados.json").write_text(json.dumps(results), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(meta or {"model": label}), encoding="utf-8")


def test_each_profile_lands_in_its_category():
    assert reg.category("9b") == "FAST sozinho" and reg.category("4b-16k-kv8") == "FAST sozinho"
    assert reg.category("9b-think") == "FAST com think"
    assert reg.category("s-gemma12") == "SMART sozinho"
    assert reg.category("par-9b+gemma12") == "Cascata (FAST + SMART)"


def test_the_evaluation_table_is_written_with_all_four_categories(tmp_path, capsys):
    fast_night, smart_night = tmp_path / "noite1", tmp_path / "noite2"
    profile_folder(fast_night, "9b", [result("soma-tres", "raciocinio", True), result("corrigir-soma", "real", False)])
    profile_folder(fast_night, "9b-think", [result("soma-tres", "raciocinio", True), result("corrigir-soma", "real", True)])
    profile_folder(smart_night, "s-gemma12", [result("tarefa3-informativo", "tarefas", True, info=True), result("corrigir-soma", "real", True)])
    profile_folder(smart_night, "par-9b+gemma12", [result("corrigir-soma", "real", True)])
    output = tmp_path / "avaliacoes.md"

    assert reg.main([str(fast_night), str(smart_night), "--saida", str(output)]) == 0

    text = output.read_text(encoding="utf-8")

    assert "| FAST sozinho | 9b | 1/2 (50%) | 1/1 | 0/1 |" in text
    assert "| FAST com think | 9b-think |" in text and "| SMART sozinho | s-gemma12 |" in text and "passou" in text
    assert "| Cascata (FAST + SMART) | par-9b-gemma12 |" in text or "| Cascata (FAST + SMART) | par-9b+gemma12 |" in text
    assert "as quatro foram medidas" in text


def test_missing_categories_are_named(tmp_path):
    folder = tmp_path / "noite"
    profile_folder(folder, "9b", [result("a", "simples", True)])
    output = tmp_path / "avaliacoes.md"

    reg.main([str(folder), "--saida", str(output)])

    assert "Categorias sem dados nesta rodada: FAST com think, SMART sozinho, Cascata (FAST + SMART)" in output.read_text(encoding="utf-8")


def test_no_results_means_a_clear_message_and_no_file(tmp_path, capsys):
    output = tmp_path / "avaliacoes.md"

    assert reg.main([str(tmp_path / "vazia"), "--saida", str(output)]) == 1
    assert not output.exists() and "Rode o comparar.bat" in capsys.readouterr().out


# ---------------------------------------------------------
# Itens que já estavam feitos
# ---------------------------------------------------------

def test_the_items_already_implemented_are_ticked():
    text = PROJECT_SPEC_PATH.read_text(encoding="utf-8")

    for item in ("Definir gatilho de compactação", "Testar troca de modelo durante tarefa", "Permitir criação controlada de novas Skills",
                 "Criar Model Registry", "Criar sistema de candidatos"):
        assert f"* [x] {item}" in text, item
