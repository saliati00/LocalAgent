import json
import re

from core.context.metrics import describe_prompt_sections, estimate_tokens
from core.harness import logger


def test_every_log_line_carries_the_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logger, "LOG_FILE", tmp_path / "agent.log")

    run_id = logger.new_run_id()
    logger.log("ONE", "a")
    logger.log("TWO")

    lines = (tmp_path / "agent.log").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    for line in lines:
        assert re.match(rf"^\[[\d\- :]+\] \[{run_id}\] \w+", line)

    assert logger.new_run_id() != run_id


def test_logger_default_dir_is_the_project_logs_dir():
    from core.paths import LOGS_DIR, PROJECT_ROOT

    # LOG_DIR é redirecionado pelo conftest; o padrão vem de core.paths.
    assert logger.LOGS_DIR == LOGS_DIR == PROJECT_ROOT / "logs"


def test_prompt_sections_report_sizes_and_total():
    report = json.loads(describe_prompt_sections(
        {"skills": "a" * 300, "memory": "b" * 90},
        context_window=1000,
    ))

    assert report["skills"]["chars"] == 300
    assert report["memory"]["chars"] == 90
    assert report["_total"]["chars"] == 390
    assert report["_total"]["est_tokens"] == estimate_tokens("a" * 300) + estimate_tokens("b" * 90)
    assert 0 < report["_total"]["fraction_of_window"] < 1


def test_detail_sections_are_reported_but_not_double_counted():
    report = json.loads(describe_prompt_sections({
        "system_instructions": "a" * 300,
        "tools_schema": "b" * 90,
        "detail:skills": "c" * 120,
    }))

    assert report["detail:skills"]["chars"] == 120
    assert report["_total"]["chars"] == 390


def test_fast_model_does_not_receive_propose_skill_schema():
    import agent

    fast = {t["function"]["name"] for t in agent.visible_tools(False)}
    smart = {t["function"]["name"] for t in agent.visible_tools(True)}

    assert "propose_skill" not in fast
    assert "propose_skill" in smart
    assert smart - fast == {"propose_skill"}


# ---------------------------------------------------------
# Velocidade de geração
# ---------------------------------------------------------

def test_tokens_per_second_prefers_the_ollama_generation_time():
    from core.context.metrics import tokens_per_second

    # 50 tokens em 2 s de geração (2e9 ns), mesmo que a chamada toda tenha levado 10 s
    assert tokens_per_second(50, 2_000_000_000, 10.0) == 25.0


def test_tokens_per_second_falls_back_to_wall_time_and_handles_missing_data():
    from core.context.metrics import tokens_per_second

    assert tokens_per_second(50, None, 5.0) == 10.0
    assert tokens_per_second(50, 0, 5.0) == 10.0
    assert tokens_per_second(0, 1_000_000_000, 5.0) is None
    assert tokens_per_second(50, None, 0) is None


def test_agent_logs_seconds_and_speed_per_model_call(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import agent
    from core.harness import logger

    response = SimpleNamespace(
        message=SimpleNamespace(role="assistant", content="ok", tool_calls=None),
        prompt_eval_count=500,
        eval_count=40,
        eval_duration=2_000_000_000,
    )

    monkeypatch.setattr(agent.client, "chat", lambda *a, **k: response)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(agent, "check_completion", lambda **kw: {"status": "complete", "reason": "ok"})

    agent.agent("Diga ok")

    line = [l for l in logger.LOG_FILE.read_text(encoding="utf-8").splitlines() if " TOKENS | " in l][0]

    assert "seconds=" in line
    assert "tok_s=20.0" in line


def test_summarize_logs_reports_speed_and_call_time():
    from scripts import summarize_logs

    lines = [
        "[2026-10-06 10:00:00] [aaaa1111] TOKENS | input=2000 | output=40 | total=2040 | seconds=6.0 | tok_s=20.0",
        "[2026-10-06 10:00:10] [aaaa1111] TOKENS | input=2100 | output=30 | total=2130 | seconds=4.0 | tok_s=10.0",
        "[2026-10-06 10:00:20] [bbbb2222] TOKENS | input=2200 | output=20 | total=2220",
    ]

    report = summarize_logs.summarize(lines)

    assert report["generation_tokens_per_second"] == {"count": 2, "avg": 15.0, "min": 10.0, "max": 20.0}
    assert report["seconds_per_call"]["avg"] == 5.0
    assert report["model_calls"] == 3
