"""Comparação de modelos: troca de FAST só por variável de ambiente e relatório lado a lado."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import comparar_modelos as cmp  # noqa: E402
import bateria  # noqa: E402
from core.router.model_router import FAST_MODEL_ENV, ModelRouter  # noqa: E402


def run(id, passed, group="simples", info=False, tok_s=60.0, seconds=10.0, tools=2, failed=0, events=None, violations=None):
    return {"id": id, "passed": passed, "group": group, "info": info, "tok_s": tok_s, "seconds": seconds,
            "tools": tools, "failed_tools": failed, "events": events or {}, "violations": violations or [],
            "status": "completed", "attempt": 1, "detail": ""}


def entry(label, results, **extra):
    return {"label": label, "results": results, "meta": {"ollama_ps": f"{label} 100% GPU"}, **extra}


def test_fast_model_can_be_overridden_by_environment_without_touching_registry(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"active_fast_model": "qwen3:8b", "models": {}}), encoding="utf-8")
    router = ModelRouter(registry)

    assert router.get_fast_model() == "qwen3:8b"

    monkeypatch.setenv(FAST_MODEL_ENV, "qwen3.5:9b")

    assert router.get_fast_model() == "qwen3.5:9b"
    assert router.route_task("oi") == "qwen3.5:9b"
    assert json.loads(registry.read_text(encoding="utf-8"))["active_fast_model"] == "qwen3:8b"


def test_blank_override_is_ignored(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"active_fast_model": "qwen3:8b", "models": {}}), encoding="utf-8")
    monkeypatch.setenv(FAST_MODEL_ENV, "   ")

    assert ModelRouter(registry).get_fast_model() == "qwen3:8b"


def test_slug_is_safe_for_folder_names():
    assert cmp.slug("qwen3.5:9b") == "qwen3-5-9b"


def test_collect_reads_results_and_meta(tmp_path):
    (tmp_path / "resultados.json").write_text(json.dumps([run("a", True)]), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps({"model": "qwen3.5:4b", "ollama_ps": "x"}), encoding="utf-8")

    assert cmp.collect(tmp_path)["label"] == "qwen3.5:4b"
    assert cmp.collect(tmp_path, "outro")["label"] == "outro"
    assert cmp.collect(tmp_path / "vazia") is None


def test_collect_works_without_meta_for_runs_made_by_the_older_battery(tmp_path):
    (tmp_path / "resultados.json").write_text(json.dumps([run("a", True)]), encoding="utf-8")

    assert cmp.collect(tmp_path, "qwen3:8b")["meta"] == {}


def test_comparison_shows_winner_data_side_by_side():
    base = entry("qwen3:8b", [run("a", True), run("a", False), run("b", False, group="seguranca"), run("t3", False, group="tarefas", info=True)], smoke={"tool_call": True})
    new = entry("qwen3.5:9b", [run("a", True), run("a", True), run("b", True, group="seguranca"), run("t3", True, group="tarefas", info=True)],
                smoke={"tool_call": True})
    new["results"][0]["events"] = {"LOOP_BLOCKED": 2}

    report = cmp.build_comparison([base, new], "01/01/2027")

    assert "| qwen3:8b | 1/3 (33%)" in report
    assert "| qwen3.5:9b | 3/3 (100%)" in report
    assert "| a | 1/2 | 2/2 |" in report
    assert "info: passou" in report and "LOOP_BLOCKED | 0 | 2" in report
    assert "qwen3.5:9b 100% GPU" in report
    assert "Descarte" in report


def test_skipped_model_is_reported_with_the_reason():
    ok = entry("qwen3:8b", [run("a", True)])
    broken = {"label": "qwen3.5:9b", "results": [], "meta": {}, "skipped": "incompatível: does not support tools"}

    report = cmp.build_comparison([ok, broken], "01/01/2027")

    assert "NÃO RODOU" in report and "does not support tools" in report


def test_violations_are_counted_per_model():
    bad = entry("m", [run("a", False, violations=["agent.py"]), run("b", True)])

    assert cmp.summarize_model(bad)["violations"] == 1


def test_confirm_downloads_lists_models_and_respects_the_answer(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    assert cmp.confirm_downloads(["qwen3.5:9b"], assume_yes=False) is False
    assert "qwen3.5:9b" in capsys.readouterr().out

    assert cmp.confirm_downloads(["qwen3.5:9b"], assume_yes=True) is True
    assert cmp.confirm_downloads([], assume_yes=False) is True


def test_confirm_downloads_cancels_when_there_is_no_keyboard(monkeypatch):
    def closed(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)

    assert cmp.confirm_downloads(["qwen3.5:4b"], assume_yes=False) is False


def test_smoke_test_reports_incompatible_model(monkeypatch):
    import ollama

    class Broken:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            raise RuntimeError("model does not support tools")

    monkeypatch.setattr(ollama, "Client", Broken)

    result = cmp.smoke_test("x")

    assert result["ok"] is False and "tools" in result["error"]


def test_smoke_test_detects_a_tool_call(monkeypatch):
    import ollama

    class Fine:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            assert kwargs["think"] is False
            return SimpleNamespace(message=SimpleNamespace(tool_calls=[object()]))

    monkeypatch.setattr(ollama, "Client", Fine)

    assert cmp.smoke_test("x") == {"ok": True, "tool_call": True, "seconds": pytest.approx(0, abs=5), "error": ""}


def test_rebuild_reads_every_subfolder(tmp_path, capsys):
    for name, ok in (("a", True), ("b", False)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "resultados.json").write_text(json.dumps([run("x", ok)]), encoding="utf-8")
        (folder / "meta.json").write_text(json.dumps({"model": f"modelo-{name}"}), encoding="utf-8")

    assert cmp.rebuild(tmp_path) == 0

    text = (tmp_path / "COMPARATIVO.md").read_text(encoding="utf-8")

    assert "modelo-a" in text and "modelo-b" in text


def test_cli_table_is_plain_text_with_one_row_per_model():
    a = entry("qwen3:8b", [run("a", True, failed=1), run("b", False, failed=2)])
    b = entry("qwen3.5:4b", [run("a", True), run("b", True)])
    a["results"][0].update(tokens_in=1000, tokens_out=200)
    a["results"][1].update(tokens_in=2500, tokens_out=300)
    gone = {"label": "qwen3.5:9b", "results": [], "meta": {}, "skipped": "não instalado"}

    table = cmp.cli_table([cmp.summarize_model(e) for e in (a, b, gone)])
    rows = table.splitlines()

    assert len(rows) == 5 and "|" in rows[0] and "Tokens entrada" in rows[0]
    assert "1/2" in rows[2] and "50%" in rows[2] and "3.500" in rows[2] and "500" in rows[2]
    assert "n/d" in rows[3] and "2/2" in rows[3]
    assert "NÃO RODOU" in rows[4]
    assert "```" not in table


def test_comparison_report_starts_with_the_overview_table():
    report = cmp.build_comparison([entry("m", [run("a", True)])], "01/01/2027")

    assert report.index("## Visão geral") < report.index("## Resumo")


def test_battery_token_regex_matches_the_real_log_format():
    line = "[2026-10-07 10:00:00] [abc123] TOKENS | input=1801 | output=61 | total=1862 | seconds=1.0 | tok_s=61.0"

    found = bateria.TOKENS_LINE.search(line)

    assert (int(found.group(1)), int(found.group(2))) == (1801, 61)


def test_battery_result_has_token_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    monkeypatch.setattr(bateria, "BATERIA_DIR", tmp_path / "workspace" / "bateria")

    result = bateria.run_case(next(c for c in bateria.CASES if c["id"] == "tarefa-do-usuario"))

    assert result["tokens_in"] == 0 and result["tokens_out"] == 0
