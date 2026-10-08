"""Correções motivadas pela primeira comparação real de modelos (07/10/2026)."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bateria  # noqa: E402
import tools.manager as manager  # noqa: E402
import tools.terminal as terminal  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402
from tools.filesystem import PROTECTED_PATHS, write_file  # noqa: E402


# ---------------------------------------------------------
# mkdir nativo dentro de workspace/
# ---------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(terminal, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(terminal, "WORKSPACE_DIR", tmp_path / "workspace")
    (tmp_path / "workspace").mkdir()
    return tmp_path


def refuse_confirmation(*args, **kwargs):
    raise AssertionError("mkdir no workspace não pode pedir confirmação")


def test_mkdir_inside_workspace_is_done_natively_without_confirmation(workspace, monkeypatch):
    monkeypatch.setattr(terminal, "authorize", refuse_confirmation)

    result = terminal.run_command("mkdir workspace/bateria/multi", "criar pasta")

    assert result["success"] is True
    assert (workspace / "workspace" / "bateria" / "multi").is_dir()


def test_mkdir_accepts_the_p_flag_windows_separators_and_quotes(workspace, monkeypatch):
    monkeypatch.setattr(terminal, "authorize", refuse_confirmation)

    assert terminal.run_command("mkdir -p workspace/a/b", "criar")["success"] is True
    assert terminal.run_command('mkdir "workspace/com espaco"', "criar")["success"] is True


@pytest.mark.skipif(os.name != "nt", reason="barra invertida só é separador no Windows")
def test_mkdir_accepts_windows_backslash_paths(workspace, monkeypatch):
    monkeypatch.setattr(terminal, "authorize", refuse_confirmation)

    assert terminal.run_command("md workspace" + chr(92) + "tarefa-01", "criar")["success"] is True
    assert (workspace / "workspace" / "tarefa-01").is_dir()


@pytest.mark.parametrize("command", ["mkdir fora", "mkdir ../fora", "mkdir workspace/../fora", "mkdir /tmp/x_localagent_test"])
def test_mkdir_outside_workspace_goes_through_the_normal_confirmation(workspace, monkeypatch, command):
    asked = []

    def deny(command, reason):
        asked.append(command)
        return False

    monkeypatch.setattr(terminal, "authorize", deny)

    result = terminal.run_command(command, "criar pasta")

    assert asked == [command] and result.get("cancelled") is True
    assert not (workspace / "fora").exists()


def test_mkdir_with_unknown_flags_is_not_handled_natively(workspace, monkeypatch):
    monkeypatch.setattr(terminal, "authorize", lambda command, reason: False)

    assert terminal.run_command("mkdir -m 777 workspace/x", "criar").get("cancelled") is True


# ---------------------------------------------------------
# 'reason' em ferramentas que não o aceitam
# ---------------------------------------------------------

def test_reason_is_ignored_on_tools_that_do_not_declare_it(monkeypatch):
    seen = []
    monkeypatch.setitem(manager.TOOLS, "check_tools", lambda **kwargs: seen.append(kwargs) or {"success": True})

    result = manager.execute_tool("check_tools", {"names": ["git"], "reason": "verificar"})

    assert result["success"] is True
    assert seen == [{"names": ["git"]}]


def test_reason_is_still_required_where_declared(monkeypatch):
    result = manager.execute_tool("run_command", {"command": "pwd"})

    assert result["success"] is False and "reason" in result["error"]


# ---------------------------------------------------------
# Arquivos de configuração e documentação protegidos
# ---------------------------------------------------------

@pytest.mark.parametrize("relative", [
    "opencode.json", "LEIA-ME-WINDOWS.md", "ROTEIRO-DE-TESTES.md", "FAZER-EM-CASA.txt", "comparar.bat",
    "specs/ambiente.md", ".gitignore", "scripts/bateria.py", "scripts/comparar_modelos.py",
])
def test_user_config_docs_and_battery_scripts_are_protected(relative):
    assert (PROJECT_ROOT / relative).resolve() in PROTECTED_PATHS

    result = write_file(str(PROJECT_ROOT / relative), "x")

    assert result["success"] is False and "protegid" in result["error"].lower()


# ---------------------------------------------------------
# Bateria: conferências sem acento e restauração geral
# ---------------------------------------------------------

def test_checks_ignore_accents_and_case(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    (tmp_path / "a.txt").write_text("TRÊS\n", encoding="utf-8")

    assert bateria.has("a.txt", "tres")[0] is True
    assert bateria.has("a.txt", "tres", absent=("três",))[0] is False
    assert bateria.out_has(SimpleNamespace(out="Ação concluída"), "acao concluida")[0] is True


def test_every_tracked_file_changed_during_the_battery_is_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    monkeypatch.setattr(bateria, "run_cmd", lambda args: "opencode.json\nsub/dados.txt\nsumiu.txt")
    (tmp_path / "opencode.json").write_text("original", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/dados.txt").write_text("igual", encoding="utf-8")
    (tmp_path / "sumiu.txt").write_text("apagado depois", encoding="utf-8")

    snapshot = bateria.snapshot_tracked()

    (tmp_path / "opencode.json").write_text("REESCRITO PELO AGENTE", encoding="utf-8")
    (tmp_path / "sumiu.txt").unlink()

    restored = bateria.restore_changed(snapshot)

    assert sorted(restored) == ["opencode.json", "sumiu.txt"]
    assert (tmp_path / "opencode.json").read_text(encoding="utf-8") == "original"
    assert (tmp_path / "sumiu.txt").read_text(encoding="utf-8") == "apagado depois"
    assert (tmp_path / "sub/dados.txt").read_text(encoding="utf-8") == "igual"


def test_varios_arquivos_case_accepts_the_accented_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    folder = tmp_path / "workspace" / "bateria" / "multi"
    folder.mkdir(parents=True)

    for name, text in (("a.txt", "um"), ("b.txt", "dois"), ("c.txt", "três\n")):
        (folder / name).write_text(text, encoding="utf-8")

    case = next(c for c in bateria.CASES if c["id"] == "varios-arquivos")

    assert case["check"](SimpleNamespace(out=""))[0] is True
