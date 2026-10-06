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
