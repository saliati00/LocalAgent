"""PC travou ou reiniciou: o que já rodou fica salvo, o caso interrompido é registrado, a sujeira é desfeita e um perfil que derruba o PC é abandonado."""

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


def case(case_id="x", group="simples", info=False):
    return {"id": case_id, "slow": False, "info": info, "group": group, "check": lambda c: (True, "ok")}


def ok_result(case_id):
    result = bateria.failure_result(case(case_id), "ok", "completed")
    result.update(passed=True)
    return result


# ---------------------------------------------------------
# Marcador de caso em andamento
# ---------------------------------------------------------

def test_the_running_case_is_written_to_disk_before_it_starts_and_removed_after(tmp_path):
    seen = []

    def runner(case_def, attempt, folder):
        seen.append(json.loads((folder / bateria.INFLIGHT_FILE).read_text(encoding="utf-8")))
        return ok_result(case_def["id"])

    bateria.run_plan([(case("a", "real"), 2)], tmp_path, [], runner=runner, say=lambda *a, **k: None)

    assert seen[0]["id"] == "a" and seen[0]["attempt"] == 2 and seen[0]["group"] == "real"
    assert not (tmp_path / bateria.INFLIGHT_FILE).exists()


def test_a_case_that_raises_does_not_leave_the_marker_behind(tmp_path):
    def runner(case_def, attempt, folder):
        raise RuntimeError("x")

    bateria.run_plan([(case("a"), 1)], tmp_path, [], runner=runner, say=lambda *a, **k: None)

    assert not (tmp_path / bateria.INFLIGHT_FILE).exists()


def test_ctrl_c_is_not_counted_as_a_crash(tmp_path):
    def runner(case_def, attempt, folder):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        bateria.run_plan([(case("a"), 1)], tmp_path, [], runner=runner, say=lambda *a, **k: None)

    assert not (tmp_path / bateria.INFLIGHT_FILE).exists()


def test_the_first_crash_repeats_the_case_instead_of_recording_a_result(tmp_path):
    bateria.mark_inflight(tmp_path, case("conta-dois-passos", "raciocinio"), 2)
    results: list[dict] = []

    found, crashes, skipped = bateria.recover_interrupted(tmp_path, results)

    assert (found, crashes, skipped) == (True, 1, None)
    assert results == [], "sem resultado gravado o caso roda de novo"
    assert not (tmp_path / bateria.INFLIGHT_FILE).exists()
    assert bateria.read_crash_data(tmp_path)["por_caso"] == {"conta-dois-passos#2": 1}


def test_the_second_crash_in_the_same_case_skips_it(tmp_path):
    results: list[dict] = []

    bateria.mark_inflight(tmp_path, case("conta-dois-passos", "raciocinio"), 2)
    bateria.recover_interrupted(tmp_path, results)
    bateria.mark_inflight(tmp_path, case("conta-dois-passos", "raciocinio"), 2)
    found, crashes, skipped = bateria.recover_interrupted(tmp_path, results)

    assert (found, crashes, skipped) == (True, 2, "conta-dois-passos#2")
    assert results[0]["status"] == "pulado" and results[0]["infra"] is True and results[0]["passed"] is False
    assert results[0]["attempt"] == 2 and results[0]["group"] == "raciocinio"
    assert "PULADO" in results[0]["detail"]
    assert bateria.load_results(tmp_path)[0]["status"] == "pulado"


def test_crashes_in_different_cases_do_not_skip_any_of_them(tmp_path):
    results: list[dict] = []

    for case_id in ("a", "b", "c"):
        bateria.mark_inflight(tmp_path, case(case_id), 1)
        assert bateria.recover_interrupted(tmp_path, results)[2] is None

    assert results == [] and bateria.read_crashes(tmp_path) == 3


def test_a_skipped_case_is_not_run_again_by_the_plan(tmp_path):
    results: list[dict] = []
    ran = []

    for _ in range(2):
        bateria.mark_inflight(tmp_path, case("a"), 1)
        bateria.recover_interrupted(tmp_path, results)

    bateria.run_plan([(case("a"), 1), (case("b"), 1)], tmp_path, results,
                     runner=lambda c, a, f: ran.append(c["id"]) or ok_result(c["id"]), say=lambda *a, **k: None)

    assert ran == ["b"]


def test_the_old_crash_file_format_is_still_read(tmp_path):
    (tmp_path / bateria.CRASHES_FILE).write_text('{"count": 2}', encoding="utf-8")

    assert bateria.read_crashes(tmp_path) == 2 and bateria.read_crash_data(tmp_path)["por_caso"] == {}


def test_no_marker_means_no_crash_and_the_count_is_kept(tmp_path):
    (tmp_path / bateria.CRASHES_FILE).write_text('{"total": 1, "por_caso": {"a#1": 1}}', encoding="utf-8")

    assert bateria.recover_interrupted(tmp_path, []) == (False, 1, None)


def test_crashes_accumulate_across_resumes(tmp_path):
    for expected in (1, 2, 3):
        bateria.mark_inflight(tmp_path, case("a"), expected)
        assert bateria.recover_interrupted(tmp_path, [])[1] == expected


def test_a_case_that_already_has_a_result_is_not_duplicated_by_the_recovery(tmp_path):
    done = ok_result("a")
    done.update(attempt=1)
    bateria.mark_inflight(tmp_path, case("a"), 1)
    results = [done]

    bateria.recover_interrupted(tmp_path, results)

    assert len(results) == 1


def test_a_corrupt_marker_is_still_treated_as_a_crash(tmp_path):
    (tmp_path / bateria.INFLIGHT_FILE).write_text("{quebrado", encoding="utf-8")

    found, crashes, skipped = bateria.recover_interrupted(tmp_path, [])

    assert found is True and crashes == 1 and skipped is None


# ---------------------------------------------------------
# Snapshot dos arquivos versionados em disco
# ---------------------------------------------------------

def fake_commands(head="abc123", tracked="opencode.json\nsub/dados.txt"):
    def run_cmd(args):
        text = " ".join(str(a) for a in args)

        if "ls-files" in text:
            return tracked

        if "rev-parse" in text:
            return head

        return "ollama version is 9.9"

    return run_cmd


def test_snapshot_survives_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    monkeypatch.setattr(bateria, "run_cmd", fake_commands())
    (tmp_path / "opencode.json").write_text("original", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/dados.txt").write_bytes(b"\xc3\xa7\x00bin")

    bateria.save_snapshot(tmp_path, bateria.snapshot_tracked())
    head, files = bateria.load_snapshot(tmp_path)

    assert head == "abc123" and files["opencode.json"] == b"original" and files["sub/dados.txt"] == b"\xc3\xa7\x00bin"


def test_missing_or_corrupt_snapshot_loads_as_empty(tmp_path):
    assert bateria.load_snapshot(tmp_path) == (None, {})

    (tmp_path / bateria.SNAPSHOT_FILE).write_text("{quebrado", encoding="utf-8")

    assert bateria.load_snapshot(tmp_path) == (None, {})


def resume_args(folder):
    return SimpleNamespace(so="ferramentas", rapido=False, repeticoes=1, saida=str(folder), retomar=True, grupos="")


def prepare_resume(tmp_path, monkeypatch, head_now="abc123"):
    project = tmp_path / "projeto"
    project.mkdir()
    (project / "opencode.json").write_text("original", encoding="utf-8")
    folder = tmp_path / "saida"
    folder.mkdir()

    monkeypatch.setattr(bateria, "ROOT", project)
    monkeypatch.setattr(bateria, "run_cmd", fake_commands(head="abc123", tracked="opencode.json"))
    bateria.save_snapshot(folder, bateria.snapshot_tracked())

    # o PC travou no meio de um caso que tinha alterado o arquivo
    (project / "opencode.json").write_text("REESCRITO ANTES DO TRAVAMENTO", encoding="utf-8")
    bateria.mark_inflight(folder, case("ferramentas"), 1)

    monkeypatch.setattr(bateria, "run_cmd", fake_commands(head=head_now, tracked="opencode.json"))
    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(bateria, "run_in_child_once", lambda c, a, f: ok_result(c["id"]))

    return project, folder


def test_resume_undoes_what_the_interrupted_case_left_behind_and_repeats_the_case(tmp_path, monkeypatch):
    project, folder = prepare_resume(tmp_path, monkeypatch)

    bateria.orchestrate(resume_args(folder))

    assert (project / "opencode.json").read_text(encoding="utf-8") == "original"

    saved = json.loads((folder / "resultados.json").read_text(encoding="utf-8"))

    assert [r["id"] for r in saved] == ["ferramentas"] and saved[0]["passed"] is True, "o caso interrompido foi repetido"


def test_resume_does_not_restore_old_files_when_the_project_was_updated_meanwhile(tmp_path, monkeypatch, capsys):
    project, folder = prepare_resume(tmp_path, monkeypatch, head_now="def456")

    bateria.orchestrate(resume_args(folder))

    assert (project / "opencode.json").read_text(encoding="utf-8") == "REESCRITO ANTES DO TRAVAMENTO"
    assert "git pull" in capsys.readouterr().out


def test_a_profile_that_accumulates_three_crashes_is_abandoned_instead_of_looping(tmp_path, monkeypatch):
    project, folder = prepare_resume(tmp_path, monkeypatch)
    (folder / bateria.CRASHES_FILE).write_text('{"total": 2, "por_caso": {"outro#1": 1, "mais-um#1": 1}}', encoding="utf-8")
    ran = []
    monkeypatch.setattr(bateria, "run_in_child_once", lambda c, a, f: ran.append(c["id"]) or ok_result(c["id"]))

    code = bateria.orchestrate(resume_args(folder))

    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))

    assert code == 3 and ran == []
    assert "abandonado" in meta["abandoned"] and "3 vezes" in meta["abandoned"]


def test_two_crashes_in_one_case_skip_the_case_but_keep_the_profile_running(tmp_path, monkeypatch, capsys):
    project, folder = prepare_resume(tmp_path, monkeypatch)
    (folder / bateria.CRASHES_FILE).write_text('{"total": 1, "por_caso": {"ferramentas#1": 1}}', encoding="utf-8")
    ran = []
    monkeypatch.setattr(bateria, "run_in_child_once", lambda c, a, f: ran.append(c["id"]) or ok_result(c["id"]))
    args = SimpleNamespace(so="ferramentas,listar-pasta", rapido=False, repeticoes=1, saida=str(folder), retomar=True, grupos="")

    code = bateria.orchestrate(args)

    saved = {r["id"]: r for r in json.loads((folder / "resultados.json").read_text(encoding="utf-8"))}

    assert code == 0
    assert saved["ferramentas"]["status"] == "pulado" and "ferramentas" not in ran and ran == ["listar-pasta"]
    assert "PULADO" in capsys.readouterr().out
    assert "casos pulados" in (folder / "RELATORIO.md").read_text(encoding="utf-8")


def test_the_comparison_shows_an_abandoned_profile_as_not_run_with_the_reason(tmp_path):
    (tmp_path / "resultados.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps({"model": "m", "abandoned": "o PC travou 2 vezes neste perfil"}), encoding="utf-8")

    entry = cmp.collect(tmp_path, "s-coder30")
    report = cmp.build_comparison([entry], "01/01/2027")

    assert entry["skipped"].startswith("o PC travou") and "NÃO RODOU" in report


# ---------------------------------------------------------
# Vigia de memória
# ---------------------------------------------------------

class FakeProcess:
    def __init__(self, finishes_after=None):
        self.pid = 4242
        self.calls = 0
        self.finishes_after = finishes_after
        self.killed = False

    def wait(self, timeout=None):
        self.calls += 1

        if self.finishes_after is not None and self.calls >= self.finishes_after:
            return 0

        raise subprocess.TimeoutExpired("x", timeout)

    def kill(self):
        self.killed = True


def guarded(process, memory, timeout=1000, clock=None):
    killed = []
    original = cmp.kill_tree
    cmp.kill_tree = lambda p: killed.append(p)

    try:
        outcome = cmp.run_guarded(["x"], {}, ".", timeout, memory=memory, popen=lambda *a, **k: process,
                                  clock=clock or (lambda: 0), poll=1)
    finally:
        cmp.kill_tree = original

    return outcome, killed


def test_a_process_that_finishes_is_ok_and_not_killed():
    outcome, killed = guarded(FakeProcess(finishes_after=3), memory=lambda: 8000)

    assert outcome == "ok" and killed == []


def test_low_memory_for_several_polls_in_a_row_kills_the_process_before_the_pc_freezes():
    process = FakeProcess()
    outcome, killed = guarded(process, memory=lambda: 200)

    assert outcome == "memoria" and killed == [process]
    assert process.calls == cmp.LOW_MEMORY_POLLS


def test_a_memory_dip_that_recovers_does_not_abort():
    readings = iter([200, 200, 5000, 200, 200, 5000] + [5000] * 50)
    process = FakeProcess(finishes_after=20)

    outcome, killed = guarded(process, memory=lambda: next(readings))

    assert outcome == "ok" and killed == []


def test_unknown_memory_never_aborts():
    outcome, killed = guarded(FakeProcess(finishes_after=10), memory=lambda: None)

    assert outcome == "ok"


def test_exceeding_the_time_limit_kills_the_process_tree():
    ticks = iter(range(0, 10000, 400))
    process = FakeProcess()

    outcome, killed = guarded(process, memory=lambda: 8000, timeout=1000, clock=lambda: next(ticks))

    assert outcome == "timeout" and killed == [process]


def test_run_one_records_why_a_profile_was_cut_by_memory_and_unloads_the_model(tmp_path, monkeypatch):
    stopped = []
    monkeypatch.setattr(cmp, "run_guarded", lambda *a, **k: "memoria")
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: stopped.append(model))
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)

    finished = cmp.run_one(cmp.profile_from_model("m"), tmp_path, SimpleNamespace(repeticoes=1, rapido=False, limite_modelo=5))

    assert finished is False and stopped == ["m"]
    assert "memória livre" in (tmp_path / "abortado.txt").read_text(encoding="utf-8")


def test_the_comparison_flags_a_profile_cut_by_memory(tmp_path):
    result = {"id": "a", "passed": True, "group": "simples", "info": False, "tok_s": 5.0, "seconds": 1.0, "tools": 1,
              "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}
    (tmp_path / "resultados.json").write_text(json.dumps([result]), encoding="utf-8")
    (tmp_path / "abortado.txt").write_text("a memória livre ficou abaixo de 700 MB", encoding="utf-8")

    entry = cmp.collect(tmp_path, "s-coder30")
    report = cmp.build_comparison([entry], "01/01/2027")

    assert "perfis interrompidos" in report and "memória livre" in report


def test_resume_also_applies_when_the_pc_froze_during_the_very_first_case(tmp_path):
    assert cmp.has_progress(tmp_path) is False

    (tmp_path / "em-andamento.json").write_text("{}", encoding="utf-8")
    assert cmp.has_progress(tmp_path) is True

    (tmp_path / "em-andamento.json").unlink()
    (tmp_path / "snapshot-arquivos.json").write_text("{}", encoding="utf-8")
    assert cmp.has_progress(tmp_path) is True


def test_real_memory_reading_is_a_plausible_number_or_none():
    value = cmp.available_memory_mb()

    assert value is None or 100 < value < 4_000_000


def test_the_comparison_lists_skipped_cases_and_counts_them_outside_the_score():
    ok = {"id": "a", "passed": True, "group": "simples", "info": False, "tok_s": 50.0, "seconds": 1.0, "tools": 1,
          "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}
    skipped = {**ok, "id": "conta-dois-passos", "passed": False, "status": "pulado", "infra": True, "group": "raciocinio"}
    entry = {"label": "s-gptoss20", "results": [ok, skipped], "meta": {"ollama_ps": "ps"}}

    summary = cmp.summarize_model(entry)
    report = cmp.build_comparison([entry], "01/01/2027")

    assert summary["total"] == 1 and summary["skipped_cases"] == ["conta-dois-passos"] and summary["infra"] == 0
    assert "casos pulados porque travaram o PC" in report and "s-gptoss20: conta-dois-passos" in report
    assert "Pulados" in cmp.cli_table([summary]).splitlines()[0]


def test_the_battery_report_marks_skipped_cases_distinctly():
    ok = bateria.failure_result(case("a"), "ok", "completed")
    ok.update(passed=True, attempt=1, group="simples", info=False)
    skipped = bateria.failure_result(case("b"), "PULADO: travou", "pulado", infra=True)
    skipped.update(attempt=1, group="simples", info=False)
    meta = {"date": "01/01/2027", "ollama_version": "x", "minutes": 1.0, "ollama_ps": "ps", "restored": [], "git_status": ""}

    report = bateria.build_report([ok, skipped], meta)

    assert "1 de 1 execuções passaram" in report and "PULADO" in report
    assert "casos pulados porque travaram o PC" in report
    assert "Falhas de infraestrutura (Ollama fora do ar; não contam contra o modelo): 0" in report
