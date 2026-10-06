import os
import sys
from pathlib import Path

import pytest

from core.harness.permissions import parse_command, requires_confirmation
from core.paths import PROJECT_ROOT, VENV_BIN_DIR
from tools.terminal import check_constraints, run_command
from core.harness.task_constraints import TaskConstraints


# ---------------------------------------------------------
# Comandos "seguros" não podem executar/alterar nada
# ---------------------------------------------------------

def test_find_with_delete_or_exec_requires_confirmation():
    assert requires_confirmation("find . -name x.txt") is False
    assert requires_confirmation("find . -delete") is True
    assert requires_confirmation("find . -exec rm {} ;") is True
    assert requires_confirmation("find . -execdir rm {} ;") is True
    assert requires_confirmation("find . -fprint out.txt") is True


def test_pytest_only_safe_inside_tests_dir():
    assert requires_confirmation("pytest") is False
    assert requires_confirmation("pytest -v") is False
    assert requires_confirmation("pytest tests/test_memory.py -q") is False
    assert requires_confirmation("pytest -k memory") is False
    assert requires_confirmation("pytest agent.py") is True
    assert requires_confirmation("pytest -p some.plugin") is True
    assert requires_confirmation("pytest -c other.ini") is True
    assert requires_confirmation("pytest --rootdir=. workspace") is True


# ---------------------------------------------------------
# Restrições de tarefa precisam valer no fluxo real do agente
# ---------------------------------------------------------

def _constraints(**kw):
    c = TaskConstraints()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_agent_constraint_blocks_wrapped_install():
    import agent

    c = _constraints(allow_install=False)
    for cmd in ("sudo dnf install git", "env pip install requests", "pip install requests"):
        res = agent.check_task_constraint("run_command", {"command": cmd}, c)
        assert res is not None and res["constraint_blocked"], cmd

    assert agent.check_task_constraint("run_command", {"command": "pip list"}, c) is None


def test_agent_constraint_blocks_windows_install_tools():
    import agent

    c = _constraints(allow_install=False)
    for cmd in ("winget install git", "choco install git", "scoop install git"):
        res = agent.check_task_constraint("run_command", {"command": cmd}, c)
        assert res is not None and res["constraint_blocked"], cmd


def test_check_constraints_destructive_windows():
    c = _constraints(allow_destructive=False)
    for cmd in ("del file.txt", "rd /s folder", "Remove-Item x"):
        parts, _ = parse_command(cmd)
        res = check_constraints(parts, c)
        assert res is not None and res["constraint_blocked"], cmd


# ---------------------------------------------------------
# Parsing no Windows: caminhos com barra invertida e aspas
# ---------------------------------------------------------

def test_parse_command_keeps_windows_backslashes():
    parts, err = parse_command(r'python C:\Users\x\script.py "C:\Program Files\a b.txt"')
    assert err is None
    if os.name == "nt":
        assert parts == ["python", r"C:\Users\x\script.py", r"C:\Program Files\a b.txt"]


# ---------------------------------------------------------
# Execução real, independente de SO
# ---------------------------------------------------------

def test_run_command_python_version():
    res = run_command("python --version", "Verificar versão do Python")
    assert res["success"] is True
    assert "Python" in (res["stdout"] + res["stderr"])


def test_run_command_runs_in_project_root():
    res = run_command(
        'python -c "import os; print(os.getcwd())"',
        "Verificar diretório de trabalho",
    )
    # python -c requer confirmação; em ambiente não interativo é cancelado
    assert res["success"] is False or Path(res["stdout"].strip()).resolve() == PROJECT_ROOT


def test_venv_bin_dir_matches_platform():
    assert VENV_BIN_DIR.name == ("Scripts" if os.name == "nt" else "bin")


# ---------------------------------------------------------
# PowerShell: somente cmdlets de leitura são seguros
# ---------------------------------------------------------

def test_powershell_read_only_cmdlets_are_safe():
    assert requires_confirmation('powershell -NoProfile -Command "Get-ChildItem"') is False
    assert requires_confirmation('powershell -Command "Get-Command git"') is False
    assert requires_confirmation('powershell -Command "Remove-Item x"') is True
    assert requires_confirmation('powershell -Command "Set-Content a.txt b"') is True
    assert requires_confirmation("powershell -File script.ps1") is True
    assert requires_confirmation("cmd /c dir") is True
