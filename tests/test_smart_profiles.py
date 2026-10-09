"""Candidatos a SMART na bateria: perfis só com os grupos difíceis, mais tempo, e pareamento FAST+SMART."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agent  # noqa: E402
import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402
from core.router.model_router import SMART_MODEL_ENV, ModelRouter  # noqa: E402


def args(**overrides):
    base = dict(modelos="", perfis="", repeticoes=2, rapido=False, limite_modelo=5)
    base.update(overrides)
    return SimpleNamespace(**base)


def result(case_id="a", group="simples", info=False, passed=True):
    return {"id": case_id, "passed": passed, "group": group, "info": info, "tok_s": 50.0, "seconds": 1.0, "tools": 1,
            "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}


# ---------------------------------------------------------
# Perfis
# ---------------------------------------------------------

def test_smart_candidates_are_the_verified_ollama_models_and_run_after_the_fast_profiles():
    assert cmp.DEFAULT_PROFILES == cmp.FAST_PROFILES + cmp.SMART_PROFILES
    assert cmp.PROFILES["s-gemma12"]["model"] == "gemma4:12b"
    assert cmp.PROFILES["s-gptoss20"]["model"] == "gpt-oss:20b"
    assert cmp.PROFILES["s-coder30"]["model"] == "qwen3-coder:30b"
    assert cmp.SMART_PROFILES[-1] == "s-coder30", "o maior (19 GB, no limite da RAM) fica por último"


def test_smart_profiles_run_only_the_hard_groups_once_with_extra_time():
    for name in ("s-gemma12", "s-gptoss20", "s-coder30"):
        profile = cmp.PROFILES[name]

        assert profile["role"] == "smart" and profile["grupos"] == "raciocinio,real,tarefas" and profile["repeticoes"] == 1
        assert profile["timeout_factor"] > 1 and profile["call_timeout"] > 120 and profile["limite"] > 6000
        assert profile["server"] == cmp.KV8


def test_the_paired_profile_is_a_fast_model_that_escalates_to_a_smart_one():
    pair = cmp.PROFILES["par-9b+gemma12"]

    assert pair["model"] == "qwen3.5:9b" and pair["smart_model"] == "gemma4:12b"
    assert pair["grupos"] == "real,tarefas"


def test_profile_groups_expand_and_deduplicate():
    assert [p["label"] for p in cmp.resolve_profiles(args(perfis="smart"))] == cmp.SMART_PROFILES
    assert [p["label"] for p in cmp.resolve_profiles(args())] == cmp.DEFAULT_PROFILES
    assert [p["label"] for p in cmp.resolve_profiles(args(perfis="9b,fast"))] == cmp.FAST_PROFILES


def test_download_sizes_are_known_for_every_model_of_every_profile():
    models = {m for p in cmp.PROFILES.values() for m in (p["model"], p.get("smart_model")) if m}

    assert models <= set(cmp.APPROX_DOWNLOAD_GB)


# ---------------------------------------------------------
# O que o perfil muda na execução
# ---------------------------------------------------------

def run_one_env(profile, tmp_path, monkeypatch):
    seen = {"stopped": []}

    def fake_guarded(command, env, cwd, timeout, **kwargs):
        seen["command"], seen["env"], seen["timeout"] = command, env, timeout
        return "ok"

    monkeypatch.setattr(cmp, "run_guarded", fake_guarded)
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: seen["stopped"].append(model))
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)

    cmp.run_one(profile, tmp_path, args(), url="http://127.0.0.1:11435")

    return seen


def test_smart_profile_passes_groups_repetitions_time_factor_and_call_timeout(tmp_path, monkeypatch):
    seen = run_one_env({"label": "s-x", **cmp.PROFILES["s-gptoss20"]}, tmp_path, monkeypatch)

    command, env = seen["command"], seen["env"]

    assert command[command.index("--grupos") + 1] == "raciocinio,real,tarefas"
    assert command[command.index("--repeticoes") + 1] == "1"
    assert env["LOCALAGENT_TIMEOUT_FACTOR"] == "3" and env["LOCALAGENT_CALL_TIMEOUT"] == "600"
    assert env["LOCALAGENT_FAST_MODEL"] == "gpt-oss:20b" and "LOCALAGENT_SMART_MODEL" not in env
    assert seen["timeout"] == 10800


def test_paired_profile_exports_the_smart_model_and_unloads_both_models(tmp_path, monkeypatch):
    seen = run_one_env({"label": "par", **cmp.PROFILES["par-9b+gemma12"]}, tmp_path, monkeypatch)

    assert seen["env"]["LOCALAGENT_FAST_MODEL"] == "qwen3.5:9b"
    assert seen["env"]["LOCALAGENT_SMART_MODEL"] == "gemma4:12b"
    assert seen["stopped"] == ["qwen3.5:9b", "gemma4:12b"]


def test_fast_profile_keeps_the_default_timeouts_and_all_groups(tmp_path, monkeypatch):
    seen = run_one_env({"label": "9b", **cmp.PROFILES["9b"]}, tmp_path, monkeypatch)

    assert "--grupos" not in seen["command"]
    assert seen["timeout"] == 5


# ---------------------------------------------------------
# Bateria: grupos e tempo
# ---------------------------------------------------------

def test_battery_can_be_limited_to_groups_and_rejects_unknown_ones():
    chosen = bateria.select_cases(SimpleNamespace(so=None, rapido=False, grupos="raciocinio, real"))

    assert {c["group"] for c in chosen} == {"raciocinio", "real"}

    with pytest.raises(SystemExit):
        bateria.select_cases(SimpleNamespace(so=None, rapido=False, grupos="nao-existe"))


def test_hard_groups_keep_the_numbered_task_three_and_drop_the_easy_groups():
    everything = bateria.select_cases(SimpleNamespace(so=None, rapido=False, grupos=""))
    hard = bateria.select_cases(SimpleNamespace(so=None, rapido=False, grupos="raciocinio,real,tarefas"))

    assert len(hard) < len(everything)
    assert "tarefa3-informativo" in {c["id"] for c in hard}
    assert not {c["group"] for c in hard} & {"simples", "seguranca"}


def test_timeout_factor_is_read_from_the_environment_and_is_bounded(monkeypatch):
    monkeypatch.delenv("LOCALAGENT_TIMEOUT_FACTOR", raising=False)
    assert bateria.timeout_factor() == 1.0

    monkeypatch.setenv("LOCALAGENT_TIMEOUT_FACTOR", "3")
    assert bateria.timeout_factor() == 3.0

    for bad in ("abc", "0", "50", "-2"):
        monkeypatch.setenv("LOCALAGENT_TIMEOUT_FACTOR", bad)
        assert bateria.timeout_factor() == 1.0


def test_case_time_limit_grows_with_the_factor(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(bateria.subprocess, "run", lambda command, **kwargs: seen.append(kwargs["timeout"]) or SimpleNamespace(stdout="", stderr=""))
    monkeypatch.setenv("LOCALAGENT_TIMEOUT_FACTOR", "3")

    bateria.run_in_child_once({"id": "x", "slow": False, "approve": False}, 1, tmp_path)

    assert seen == [bateria.DEFAULT_TIMEOUT * 3]


# ---------------------------------------------------------
# Roteador e agente
# ---------------------------------------------------------

def test_smart_model_can_come_from_the_environment_without_touching_the_registry(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text('{"active_fast_model": "f", "active_smart_model": null, "models": {}}', encoding="utf-8")
    router = ModelRouter(registry)

    assert router.get_smart_model() is None
    assert router.check_smart_availability()[0] is False

    monkeypatch.setenv(SMART_MODEL_ENV, "gemma4:12b")

    assert router.get_smart_model() == "gemma4:12b"
    assert registry.read_text(encoding="utf-8").count("gemma4") == 0


def test_environment_smart_must_be_installed_to_be_available(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text('{"active_fast_model": "f", "models": {}}', encoding="utf-8")
    router = ModelRouter(registry)
    monkeypatch.setenv(SMART_MODEL_ENV, "gemma4:12b")

    available, reason, diag = router.check_smart_availability(backend_checker=lambda name: True)

    assert available is True and diag["source"] == "environment"

    available, reason, diag = router.check_smart_availability(backend_checker=lambda name: False)

    assert available is False and "não está instalado" in reason


def test_blank_smart_override_is_ignored(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text('{"active_smart_model": null, "models": {}}', encoding="utf-8")
    monkeypatch.setenv(SMART_MODEL_ENV, "   ")

    assert ModelRouter(registry).get_smart_model() is None


def test_agent_call_timeout_is_configurable_and_bounded(monkeypatch):
    monkeypatch.delenv("LOCALAGENT_CALL_TIMEOUT", raising=False)
    assert agent._float_from_environment("LOCALAGENT_CALL_TIMEOUT", 120) == 120

    monkeypatch.setenv("LOCALAGENT_CALL_TIMEOUT", "600")
    assert agent._float_from_environment("LOCALAGENT_CALL_TIMEOUT", 120) == 600

    for bad in ("abc", "1", "99999"):
        monkeypatch.setenv("LOCALAGENT_CALL_TIMEOUT", bad)
        assert agent._float_from_environment("LOCALAGENT_CALL_TIMEOUT", 120) == 120


# ---------------------------------------------------------
# Relatório
# ---------------------------------------------------------

def test_report_explains_how_to_choose_the_smart_when_smart_profiles_are_present():
    entry = {"label": "s-gemma12", "results": [result("tarefa3-informativo", "tarefas", info=True)], "meta": {"ollama_ps": "ps"},
             "profile": {"label": "s-gemma12", **cmp.PROFILES["s-gemma12"]}}

    report = cmp.build_comparison([entry], "01/01/2027")

    assert "## Escolhendo o SMART" in report and "tarefa 3" in report
    assert "| s-gemma12 | smart | gemma4:12b | 8192 |" in report and "raciocinio,real,tarefas" in report


def test_report_has_no_smart_section_for_fast_only_runs():
    entry = {"label": "9b", "results": [result()], "meta": {"ollama_ps": "ps"}, "profile": {"label": "9b", **cmp.PROFILES["9b"]}}

    assert "## Escolhendo o SMART" not in cmp.build_comparison([entry], "01/01/2027")
