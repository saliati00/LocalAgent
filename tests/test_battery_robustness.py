"""A bateria não pode desperdiçar uma rodada: um caso que falha, trava ou derruba o Ollama não pára os demais."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402


def case(case_id="x", slow=False, info=False, group="simples"):
    return {"id": case_id, "slow": slow, "info": info, "group": group, "check": lambda c: (True, "ok")}


def ok_result(case_id, **extra):
    base = bateria.failure_result(case(case_id), "ok", "completed")
    base.update(passed=True, **extra)
    return base


def quiet(*args, **kwargs):
    return None


# ---------------------------------------------------------
# Um erro num caso não pára os outros
# ---------------------------------------------------------

def test_exception_in_one_case_does_not_stop_the_rest(tmp_path):
    plan = [(case("a"), 1), (case("b"), 1), (case("c"), 1)]
    results: list[dict] = []

    def runner(case_def, attempt, folder):
        if case_def["id"] == "b":
            raise RuntimeError("explodiu")

        return ok_result(case_def["id"])

    bateria.run_plan(plan, tmp_path, results, runner=runner, say=quiet)

    assert [r["id"] for r in results] == ["a", "b", "c"]
    assert results[1]["passed"] is False and results[1]["status"] == "erro-interno"
    assert "explodiu" in results[1]["detail"]
    assert results[2]["passed"] is True


def test_results_are_saved_to_disk_after_every_case(tmp_path):
    plan = [(case("a"), 1), (case("b"), 1)]
    snapshots = []

    def runner(case_def, attempt, folder):
        snapshots.append(len(bateria.load_results(folder)))
        return ok_result(case_def["id"])

    bateria.run_plan(plan, tmp_path, [], runner=runner, say=quiet)

    assert snapshots == [0, 1]
    assert len(bateria.load_results(tmp_path)) == 2


def test_resume_skips_what_is_already_done(tmp_path):
    done = ok_result("a")
    done.update(attempt=1)
    results = [done]
    called = []

    def runner(case_def, attempt, folder):
        called.append((case_def["id"], attempt))
        return ok_result(case_def["id"])

    bateria.run_plan([(case("a"), 1), (case("a"), 2), (case("b"), 1)], tmp_path, results, runner=runner, say=quiet)

    assert called == [("a", 2), ("b", 1)]
    assert len(results) == 3


def test_corrupt_progress_file_is_treated_as_empty(tmp_path):
    (tmp_path / "resultados.json").write_text("{quebrado", encoding="utf-8")

    assert bateria.load_results(tmp_path) == []


def test_tracked_files_changed_by_a_case_are_restored_before_the_next_one(tmp_path):
    changes = iter([["opencode.json"], []])
    results: list[dict] = []

    bateria.run_plan([(case("a"), 1), (case("b"), 1)], tmp_path, results,
                     runner=lambda c, a, f: ok_result(c["id"]), restore=lambda: next(changes), say=quiet)

    assert results[0]["tracked_changed"] == ["opencode.json"]
    assert results[1]["tracked_changed"] == []


def test_a_failing_restore_does_not_stop_the_battery(tmp_path):
    def broken():
        raise OSError("disco")

    results: list[dict] = []

    bateria.run_plan([(case("a"), 1), (case("b"), 1)], tmp_path, results,
                     runner=lambda c, a, f: ok_result(c["id"]), restore=broken, say=quiet)

    assert len(results) == 2


# ---------------------------------------------------------
# Ollama fora do ar: tenta recuperar e não culpa o modelo
# ---------------------------------------------------------

def test_case_is_retried_after_ollama_comes_back(tmp_path):
    attempts = []

    def runner(case_def, attempt, folder):
        attempts.append(1)

        if len(attempts) == 1:
            failed = bateria.failure_result(case_def, "Connection refused", "failed", infra=True)
            return failed

        return ok_result(case_def["id"])

    result = bateria.run_in_child(case(), 1, tmp_path, runner=runner, ensure=lambda: True)

    assert result["passed"] is True and len(attempts) == 2


def test_persistent_outage_is_marked_as_infrastructure_not_as_a_model_failure(tmp_path):
    def runner(case_def, attempt, folder):
        return bateria.failure_result(case_def, "Connection refused", "failed", infra=True)

    result = bateria.run_in_child(case(), 1, tmp_path, runner=runner, ensure=lambda: True, retries=2)

    assert result["passed"] is False and result["infra"] is True
    assert result["detail"].startswith("FALHA DE INFRA")


def test_ollama_never_coming_back_does_not_run_the_case_at_all(tmp_path):
    ran = []

    result = bateria.run_in_child(case(), 1, tmp_path, runner=lambda *a: ran.append(1), ensure=lambda: False, retries=1)

    assert ran == [] and result["infra"] is True and result["status"] == "infra"


def test_ordinary_failure_is_not_retried_or_marked_infra(tmp_path):
    attempts = []

    def runner(case_def, attempt, folder):
        attempts.append(1)
        return bateria.failure_result(case_def, "o arquivo não foi criado", "completed")

    result = bateria.run_in_child(case(), 1, tmp_path, runner=runner, ensure=lambda: True)

    assert len(attempts) == 1 and not result.get("infra")
    assert not result["detail"].startswith("FALHA DE INFRA")


def test_ensure_ollama_does_nothing_when_it_is_already_up(monkeypatch):
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5: True)
    monkeypatch.setattr(bateria.subprocess, "Popen", lambda *a, **k: pytest.fail("não devia subir de novo"))

    assert bateria.ensure_ollama() is True


def test_ensure_ollama_starts_the_server_and_waits(monkeypatch):
    states = iter([False, False, True])
    started = []

    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5: next(states))
    monkeypatch.setattr(bateria.subprocess, "Popen", lambda *a, **k: started.append(a))
    monkeypatch.setattr(bateria.time, "sleep", lambda s: None)

    assert bateria.ensure_ollama(wait_seconds=30) is True
    assert started


def test_ensure_ollama_gives_up_when_it_cannot_start(monkeypatch):
    monkeypatch.setattr(bateria, "ollama_alive", lambda timeout=5: False)

    def cannot(*args, **kwargs):
        raise OSError("sem ollama")

    monkeypatch.setattr(bateria.subprocess, "Popen", cannot)

    assert bateria.ensure_ollama() is False


# ---------------------------------------------------------
# Filho com defeito: nunca derruba o pai
# ---------------------------------------------------------

def fake_run(output="", exc=None):
    def runner(*args, **kwargs):
        if exc:
            raise exc

        return SimpleNamespace(stdout=output, stderr="")

    return runner


def test_child_with_garbage_output_becomes_a_failure_result(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria.subprocess, "run", fake_run("lixo sem marcador"))

    result = bateria.run_in_child_once(case("g"), 1, tmp_path)

    assert result["passed"] is False and result["status"] == "sem-resultado"
    assert (tmp_path / "g-1.txt").exists()


def test_child_with_invalid_json_result_becomes_a_failure_result(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria.subprocess, "run", fake_run(bateria.RESULT_MARK + "{quebrado"))

    assert bateria.run_in_child_once(case("j"), 1, tmp_path)["status"] == "sem-resultado"


def test_child_timeout_becomes_a_timeout_result(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria.subprocess, "run", fake_run(exc=subprocess.TimeoutExpired("x", 5, output="parcial")))

    result = bateria.run_in_child_once(case("t"), 1, tmp_path)

    assert result["status"] == "timeout" and "tempo limite" in result["detail"]
    assert (tmp_path / "t-1.txt").read_text(encoding="utf-8") == "parcial"


def test_child_that_cannot_start_becomes_an_internal_error_result(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria.subprocess, "run", fake_run(exc=OSError("sem python")))

    assert bateria.run_in_child_once(case("o"), 1, tmp_path)["status"] == "erro-interno"


def test_connection_errors_in_the_transcript_mark_the_failure_as_infrastructure(tmp_path, monkeypatch):
    failed = bateria.failure_result(case("i"), "x", "failed")
    output = "httpx.ConnectError: [WinError 10061] Connection refused\n" + bateria.RESULT_MARK + json.dumps(failed)
    monkeypatch.setattr(bateria.subprocess, "run", fake_run(output))

    assert bateria.run_in_child_once(case("i"), 1, tmp_path)["infra"] is True


def test_a_passing_case_is_never_marked_infrastructure(tmp_path, monkeypatch):
    passed = ok_result("p")
    output = "Connection refused (tentativa antiga)\n" + bateria.RESULT_MARK + json.dumps(passed)
    monkeypatch.setattr(bateria.subprocess, "run", fake_run(output))

    assert bateria.run_in_child_once(case("p"), 1, tmp_path)["infra"] is False


# ---------------------------------------------------------
# Relatório
# ---------------------------------------------------------

META = {"date": "01/01/2027", "ollama_version": "x", "minutes": 1.0, "ollama_ps": "ps", "restored": [], "git_status": ""}


def full(case_id, passed, **extra):
    result = bateria.failure_result(case(case_id), "d", "completed")
    result.update(passed=passed, attempt=1, group="simples", info=False, **extra)
    return result


def test_infrastructure_failures_do_not_count_against_the_model():
    results = [full("a", True), full("b", False), full("c", False, infra=True)]

    report = bateria.build_report(results, META)

    assert "1 de 2 execuções passaram" in report
    assert "Falhas de infraestrutura" in report and ": 1" in report
    assert "INFRA" in report


def test_report_lists_cases_that_changed_tracked_files():
    results = [full("a", True, tracked_changed=["opencode.json"])]

    assert "opencode.json" in bateria.build_report(results, META)


def test_a_broken_report_falls_back_to_a_reduced_one_instead_of_crashing():
    broken = [{"id": "z", "passed": True}]

    report = bateria.safe_report(broken, META)

    assert "versão reduzida" in report and "z" in report


def test_keep_awake_runs_the_body_and_never_raises():
    ran = []

    with bateria.keep_awake():
        ran.append(1)

    assert ran == [1]


# ---------------------------------------------------------
# Comparação de modelos
# ---------------------------------------------------------

def args(**overrides):
    base = dict(repeticoes=2, rapido=False, limite_modelo=5)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_collect_survives_a_corrupt_results_file(tmp_path):
    (tmp_path / "resultados.json").write_text("{quebrado", encoding="utf-8")

    assert cmp.collect(tmp_path) is None


def test_a_model_that_exceeds_its_time_limit_is_stopped_and_unloaded(tmp_path, monkeypatch):
    stopped = []

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("bateria", 5)

    monkeypatch.setattr(cmp.subprocess, "run", slow)
    monkeypatch.setattr(cmp, "stop_model", stopped.append)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40: True)

    assert cmp.run_one("m", tmp_path, args()) is False
    assert stopped == ["m"]


def test_resume_flag_is_passed_to_the_battery(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cmp.subprocess, "run", lambda command, **k: seen.append(command))
    monkeypatch.setattr(cmp, "stop_model", lambda m: None)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40: True)

    cmp.run_one("m", tmp_path, args(), resume=True)

    assert "--retomar" in seen[0]


def test_wait_unloaded_returns_when_the_model_leaves_memory(monkeypatch):
    listings = iter([(0, "NAME qwen3:8b"), (0, "NAME")])
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60: next(listings))
    monkeypatch.setattr(cmp.time, "sleep", lambda s: None)

    assert cmp.wait_unloaded("qwen3:8b", seconds=30) is True


def test_wait_unloaded_gives_up_after_the_wait(monkeypatch):
    clock = iter([0, 1, 100])
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60: (0, "NAME qwen3:8b"))
    monkeypatch.setattr(cmp.time, "sleep", lambda s: None)
    monkeypatch.setattr(cmp.time, "time", lambda: next(clock))

    assert cmp.wait_unloaded("qwen3:8b", seconds=30) is False


def test_a_model_is_skipped_with_a_reason_when_ollama_is_down(tmp_path, monkeypatch):
    entries: list[dict] = []
    monkeypatch.setattr(cmp, "model_installed", lambda m: True)

    cmp.run_model("m", tmp_path, args(), entries, resume=False, ensure=lambda: False)

    assert entries[0]["skipped"] == "Ollama indisponível"


def test_resume_reuses_a_model_whose_battery_already_finished(tmp_path, monkeypatch):
    folder = tmp_path / cmp.slug("m")
    folder.mkdir()
    (folder / "resultados.json").write_text(json.dumps([ok_result("a")]), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps({"model": "m"}), encoding="utf-8")
    entries: list[dict] = []
    monkeypatch.setattr(cmp, "smoke_test", lambda m: pytest.fail("não devia testar de novo"))

    cmp.run_model("m", tmp_path, args(), entries, resume=True, ensure=lambda: True)

    assert entries[0]["label"] == "m" and entries[0]["results"]


def test_overview_table_shows_infrastructure_failures_separately():
    entry = {"label": "m", "meta": {}, "results": [ok_result("a"), bateria.failure_result(case("b"), "x", "infra", infra=True)]}
    for result in entry["results"]:
        result.update(group="simples", info=False)

    summary = cmp.summarize_model(entry)
    table = cmp.cli_table([summary])

    assert summary["total"] == 1 and summary["infra"] == 1
    assert "Falhas Ollama" in table.splitlines()[0]


def test_partial_comparison_is_written_even_when_building_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cmp, "build_comparison", lambda entries, date: (_ for _ in ()).throw(ValueError("x")))

    cmp.write_partial([], tmp_path)

    assert "não consegui atualizar" in capsys.readouterr().out


# ---------------------------------------------------------
# Fluxos completos (sem Ollama de verdade)
# ---------------------------------------------------------

def test_full_battery_flow_survives_a_crashing_case_and_still_writes_every_file(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "saida"
    calls = []

    def fake_once(case_def, attempt, target):
        calls.append(case_def["id"])

        if case_def["id"] == "criar-arquivo":
            raise RuntimeError("explodiu no meio")

        result = ok_result(case_def["id"])
        result["model_calls"] = 1
        return result

    monkeypatch.setattr(bateria, "run_cmd", lambda command: "ollama version is 9.9")
    monkeypatch.setattr(bateria, "snapshot_tracked", lambda: {})
    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(bateria, "run_in_child_once", fake_once)

    code = bateria.orchestrate(SimpleNamespace(so="ferramentas,criar-arquivo,listar-pasta", rapido=False, repeticoes=1,
                                                saida=str(folder), retomar=False))

    assert code == 0
    assert calls == ["ferramentas", "listar-pasta", "criar-arquivo"]

    saved = json.loads((folder / "resultados.json").read_text(encoding="utf-8"))

    assert [r["id"] for r in saved] == ["ferramentas", "listar-pasta", "criar-arquivo"]
    assert saved[2]["status"] == "erro-interno" and saved[1]["passed"] is True
    assert (folder / "RELATORIO.md").exists() and (folder / "meta.json").exists()


def test_battery_resumes_from_a_partial_folder(tmp_path, monkeypatch):
    folder = tmp_path / "saida"
    folder.mkdir()
    first = ok_result("ferramentas")
    first.update(attempt=1, group="simples", info=False)
    (folder / "resultados.json").write_text(json.dumps([first]), encoding="utf-8")
    calls = []

    monkeypatch.setattr(bateria, "run_cmd", lambda command: "ollama version is 9.9")
    monkeypatch.setattr(bateria, "snapshot_tracked", lambda: {})
    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(bateria, "run_in_child_once", lambda c, a, f: calls.append(c["id"]) or ok_result(c["id"]))

    bateria.orchestrate(SimpleNamespace(so="ferramentas,listar-pasta", rapido=False, repeticoes=1, saida=str(folder), retomar=True))

    assert calls == ["listar-pasta"]
    assert len(json.loads((folder / "resultados.json").read_text(encoding="utf-8"))) == 2


def test_full_comparison_flow_isolates_a_model_that_blows_up(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(cmp, "ROOT", tmp_path)
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60: (0, "ollama version is 9.9"))
    monkeypatch.setattr(cmp, "model_installed", lambda m: True)
    monkeypatch.setattr(cmp, "smoke_test", lambda m: {"ok": True, "tool_call": True, "seconds": 1, "error": ""})

    def fake_run_one(model, folder, a, resume=False):
        if model == "quebra":
            raise RuntimeError("falha esquisita")

        folder.mkdir(parents=True, exist_ok=True)
        result = ok_result("a")
        result.update(group="simples", info=False, attempt=1)
        (folder / "resultados.json").write_text(json.dumps([result]), encoding="utf-8")
        (folder / "meta.json").write_text(json.dumps({"model": model}), encoding="utf-8")
        return True

    monkeypatch.setattr(cmp, "run_one", fake_run_one)

    code = cmp.orchestrate(SimpleNamespace(modelos="bom1,quebra,bom2", base=None, base_nome="x", retomar=None, sim=True,
                                           rapido=False, repeticoes=2, limite_modelo=5))

    assert code == 0

    report = next((tmp_path / "logs" / "comparacao").iterdir()) / "COMPARATIVO.md"
    text = report.read_text(encoding="utf-8")

    assert "bom1" in text and "bom2" in text and "quebra" in text
    assert "falha esquisita" in text and "NÃO RODOU" in text
