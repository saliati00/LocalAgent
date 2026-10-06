"""Aceite da tarefa 03 (especificação do runner). Rodar: pytest -m aceite tests/test_aceite_tarefa03.py -q"""

import json
import sys

import pytest

pytestmark = pytest.mark.aceite


@pytest.fixture
def runner():
    from scripts.eval import runner as modulo

    return modulo


# ---------------------------------------------------------
# load_tasks
# ---------------------------------------------------------

def test_load_tasks_reads_json_files_in_alphabetical_order(runner, tmp_path):
    (tmp_path / "b.json").write_text(json.dumps({"id": "b"}), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps({"id": "a"}), encoding="utf-8")
    (tmp_path / "ignorar.txt").write_text("x", encoding="utf-8")

    assert [t["id"] for t in runner.load_tasks(tmp_path)] == ["a", "b"]


# ---------------------------------------------------------
# check_acceptance
# ---------------------------------------------------------

def test_file_exists_and_file_contains(runner, tmp_path):
    (tmp_path / "ola.txt").write_text("oi mundo", encoding="utf-8")

    ok, erros = runner.check_acceptance(
        [
            {"type": "file_exists", "path": "ola.txt"},
            {"type": "file_contains", "path": "ola.txt", "text": "mundo"},
        ],
        tmp_path,
    )

    assert ok is True
    assert erros == []


def test_failures_are_reported_one_message_per_criterion(runner, tmp_path):
    (tmp_path / "ola.txt").write_text("oi", encoding="utf-8")

    ok, erros = runner.check_acceptance(
        [
            {"type": "file_exists", "path": "nao_existe.txt"},
            {"type": "file_contains", "path": "ola.txt", "text": "tchau"},
            {"type": "file_exists", "path": "ola.txt"},
        ],
        tmp_path,
    )

    assert ok is False
    assert len(erros) == 2
    assert all(isinstance(e, str) and e for e in erros)


def test_command_exit_zero_runs_in_workdir_without_shell(runner, tmp_path):
    (tmp_path / "marca.txt").write_text("x", encoding="utf-8")
    python = sys.executable.replace("\\", "/")

    ok, _ = runner.check_acceptance(
        [{"type": "command_exit_zero", "command": f'"{python}" -c "import os; raise SystemExit(0 if os.path.exists(\'marca.txt\') else 1)"'}],
        tmp_path,
    )
    assert ok is True

    ok, erros = runner.check_acceptance(
        [{"type": "command_exit_zero", "command": f'"{python}" -c "raise SystemExit(3)"'}],
        tmp_path,
    )
    assert ok is False and erros


def test_command_with_shell_operators_does_not_run_a_shell(runner, tmp_path):
    runner.check_acceptance(
        [{"type": "command_exit_zero", "command": "python --version && echo pwned > feito.txt"}],
        tmp_path,
    )

    # Sem shell, "&&" e ">" viram argumentos comuns: nada é executado nem gravado.
    assert not (tmp_path / "feito.txt").exists()


@pytest.mark.parametrize("caminho", ["../fora.txt", "/etc/passwd", "C:\\Windows\\win.ini", "a/../../b.txt"])
def test_paths_outside_workdir_fail_the_criterion(runner, tmp_path, caminho):
    ok, erros = runner.check_acceptance([{"type": "file_exists", "path": caminho}], tmp_path)

    assert ok is False
    assert erros


def test_empty_criteria_do_not_count_as_success(runner, tmp_path):
    ok, erros = runner.check_acceptance([], tmp_path)

    assert ok is False
    assert erros


def test_unknown_criterion_type_fails(runner, tmp_path):
    ok, erros = runner.check_acceptance([{"type": "inventado"}], tmp_path)

    assert ok is False and erros


# ---------------------------------------------------------
# summarize
# ---------------------------------------------------------

def test_summarize_counts_runs_and_rate(runner):
    resultado = runner.summarize([
        {"task_id": "a", "passed": True},
        {"task_id": "a", "passed": False},
        {"task_id": "b", "passed": True},
        {"task_id": "b", "passed": True},
    ])

    assert resultado["total"] == 4
    assert resultado["passed"] == 3
    assert resultado["pass_rate"] == pytest.approx(0.75)
    assert resultado["by_task"] == {
        "a": {"runs": 2, "passed": 1},
        "b": {"runs": 2, "passed": 2},
    }


def test_summarize_with_no_results(runner):
    resultado = runner.summarize([])

    assert resultado["total"] == 0
    assert resultado["pass_rate"] == 0
    assert resultado["by_task"] == {}
