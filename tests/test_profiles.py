"""Perfis de teste: modelo + janela de contexto + servidor (cache de KV quantizado) sem mexer no Ollama do usuário."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent  # noqa: E402
import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402


def args(**overrides):
    base = dict(modelos="", perfis="", repeticoes=2, rapido=False, limite_modelo=5)
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------
# Escolha dos perfis
# ---------------------------------------------------------

def test_default_profiles_cover_both_models_the_kv_cache_and_the_bigger_context():
    profiles = cmp.resolve_profiles(args(perfis="fast"))
    by_label = {p["label"]: p for p in profiles}

    assert [p["label"] for p in profiles] == cmp.FAST_PROFILES
    assert by_label["9b-kv8"]["server"]["OLLAMA_KV_CACHE_TYPE"] == "q8_0"
    assert by_label["9b-kv8"]["server"]["OLLAMA_FLASH_ATTENTION"] == "1"
    assert by_label["4b-16k-kv8"]["num_ctx"] == 16384
    assert by_label["9b"]["server"] == {} and by_label["4b"]["server"] == {}
    assert by_label["8b"]["model"] == "qwen3:8b"


def test_the_most_valuable_profiles_run_first_so_a_cut_run_still_answers_the_question():
    assert cmp.FAST_PROFILES[:2] == ["9b", "4b"] and cmp.FAST_PROFILES[-1] == "8b"


def test_profiles_can_be_chosen_by_name_and_unknown_ones_are_rejected():
    assert [p["label"] for p in cmp.resolve_profiles(args(perfis="4b,9b"))] == ["4b", "9b"]

    with pytest.raises(SystemExit):
        cmp.resolve_profiles(args(perfis="9b,nao-existe"))


def test_models_option_keeps_working_with_the_default_configuration():
    profiles = cmp.resolve_profiles(args(modelos="qwen3.5:9b, gemma4:12b"))

    assert [p["label"] for p in profiles] == ["qwen3.5:9b", "gemma4:12b"]
    assert all(p["num_ctx"] == 8192 and p["server"] == {} for p in profiles)


# ---------------------------------------------------------
# Servidor do perfil
# ---------------------------------------------------------

def test_a_profile_without_server_settings_uses_the_normal_ollama(tmp_path, monkeypatch):
    monkeypatch.setattr(cmp.subprocess, "Popen", lambda *a, **k: pytest.fail("não devia subir servidor"))

    with cmp.server_for(cmp.profile_from_model("m"), tmp_path) as url:
        assert url == cmp.DEFAULT_URL


class FakeProcess:
    def __init__(self, exits_early=False):
        self.terminated = False
        self.killed = False
        self.exits_early = exits_early

    def poll(self):
        return 1 if self.exits_early else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_a_variant_profile_starts_its_own_server_on_another_port_with_the_kv_settings_and_stops_it(tmp_path, monkeypatch):
    started = {}
    process = FakeProcess()

    def popen(command, **kwargs):
        started["command"], started["env"] = command, kwargs["env"]
        return process

    monkeypatch.setattr(cmp.subprocess, "Popen", popen)
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5, url=None: True)

    with cmp.server_for({"label": "x", "model": "m", "num_ctx": 8192, "server": cmp.KV8}, tmp_path) as url:
        assert url == f"http://127.0.0.1:{cmp.VARIANT_PORT}"
        assert not process.terminated

    assert started["command"] == ["ollama", "serve"]
    assert started["env"]["OLLAMA_HOST"] == f"127.0.0.1:{cmp.VARIANT_PORT}"
    assert started["env"]["OLLAMA_KV_CACHE_TYPE"] == "q8_0" and started["env"]["OLLAMA_FLASH_ATTENTION"] == "1"
    assert process.terminated is True
    assert (tmp_path / "servidor-ollama.log").exists()


def test_the_variant_server_is_stopped_even_when_the_body_fails(tmp_path, monkeypatch):
    process = FakeProcess()
    monkeypatch.setattr(cmp.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5, url=None: True)

    with pytest.raises(ValueError):
        with cmp.server_for({"label": "x", "model": "m", "num_ctx": 8192, "server": cmp.KV8}, tmp_path):
            raise ValueError("falhou no meio")

    assert process.terminated is True


def test_a_variant_server_that_dies_on_start_is_reported_not_hung(tmp_path, monkeypatch):
    process = FakeProcess(exits_early=True)
    monkeypatch.setattr(cmp.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5, url=None: False)

    with pytest.raises(RuntimeError, match="encerrou"):
        with cmp.server_for({"label": "x", "model": "m", "num_ctx": 8192, "server": cmp.KV8}, tmp_path):
            pass

    assert process.terminated is True


def test_a_variant_server_that_never_answers_gives_up(tmp_path, monkeypatch):
    clock = iter([0, 1, 1000, 1001])
    monkeypatch.setattr(cmp.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5, url=None: False)
    monkeypatch.setattr(cmp.time, "time", lambda: next(clock))
    monkeypatch.setattr(cmp.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="não respondeu"):
        with cmp.server_for({"label": "x", "model": "m", "num_ctx": 8192, "server": cmp.KV8}, tmp_path):
            pass


def test_a_variant_that_cannot_start_becomes_a_skipped_profile_and_the_others_continue(tmp_path, monkeypatch):
    monkeypatch.setattr(cmp, "model_installed", lambda m: True)

    def broken(profile, folder):
        raise RuntimeError("o servidor do perfil não respondeu a tempo")

    monkeypatch.setattr(cmp, "server_for", broken)
    entries: list[dict] = []

    cmp.run_model({"label": "9b-kv8", "model": "qwen3.5:9b", "num_ctx": 8192, "server": cmp.KV8}, tmp_path, args(), entries, False, lambda: True)

    assert entries[0]["skipped"].startswith("o servidor do perfil") and entries[0]["profile"]["label"] == "9b-kv8"


# ---------------------------------------------------------
# O que o perfil muda na execução
# ---------------------------------------------------------

def test_run_one_passes_model_context_server_url_and_kv_settings_to_the_battery(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cmp.subprocess, "run", lambda command, **kwargs: seen.update(env=kwargs["env"]))
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: seen.update(stopped_on=url))
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)
    profile = {"label": "4b-16k-kv8", "model": "qwen3.5:4b", "num_ctx": 16384, "server": cmp.KV8}

    cmp.run_one(profile, tmp_path, args(), url="http://127.0.0.1:11435")

    env = seen["env"]

    assert env["LOCALAGENT_FAST_MODEL"] == "qwen3.5:4b" and env["LOCALAGENT_NUM_CTX"] == "16384"
    assert env["LOCALAGENT_OLLAMA_URL"] == "http://127.0.0.1:11435" and env["OLLAMA_HOST"] == "127.0.0.1:11435"
    assert env["OLLAMA_KV_CACHE_TYPE"] == "q8_0"
    assert seen["stopped_on"] == "http://127.0.0.1:11435"


def test_commands_talk_to_the_right_server():
    assert cmp.server_env("http://127.0.0.1:11435")["OLLAMA_HOST"] == "127.0.0.1:11435"


def test_the_agent_reads_the_context_window_from_the_environment(monkeypatch):
    monkeypatch.delenv("LOCALAGENT_NUM_CTX", raising=False)
    assert agent._context_from_environment() == 8192

    monkeypatch.setenv("LOCALAGENT_NUM_CTX", "16384")
    assert agent._context_from_environment() == 16384

    for bad in ("abc", "0", "999999999", "-5"):
        monkeypatch.setenv("LOCALAGENT_NUM_CTX", bad)
        assert agent._context_from_environment() == 8192


def test_battery_uses_the_server_chosen_by_the_environment(monkeypatch):
    monkeypatch.delenv("LOCALAGENT_OLLAMA_URL", raising=False)
    assert bateria.ollama_base_url() == "http://localhost:11434"

    monkeypatch.setenv("LOCALAGENT_OLLAMA_URL", "http://127.0.0.1:11435/")
    assert bateria.ollama_base_url() == "http://127.0.0.1:11435"


def test_restarting_a_variant_server_keeps_its_address(monkeypatch):
    seen = {}
    monkeypatch.setenv("LOCALAGENT_OLLAMA_URL", "http://127.0.0.1:11435")
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5, url=None: bool(seen))
    monkeypatch.setattr(bateria.subprocess, "Popen", lambda command, **kwargs: seen.update(env=kwargs["env"]))
    monkeypatch.setattr(bateria.time, "sleep", lambda s: None)

    assert bateria.ensure_ollama(wait_seconds=10) is True
    assert seen["env"]["OLLAMA_HOST"] == "127.0.0.1:11435"


# ---------------------------------------------------------
# Relatório
# ---------------------------------------------------------

def test_comparison_lists_the_profiles_that_were_tested():
    result = {"id": "a", "passed": True, "group": "simples", "info": False, "tok_s": 50.0, "seconds": 1.0, "tools": 1,
              "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}
    entry = {"label": "9b-kv8", "results": [result], "meta": {"ollama_ps": "ps"},
             "profile": {"label": "9b-kv8", "model": "qwen3.5:9b", "num_ctx": 8192, "server": cmp.KV8}}

    report = cmp.build_comparison([entry], "01/01/2027")

    assert "## Perfis testados" in report
    assert "| 9b-kv8 | fast | qwen3.5:9b | 8192 | OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0 | todos |" in report
