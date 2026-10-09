"""Erros da segunda comparação: dir/grep/type sem confirmação, dica do replace_in_file e JSON validado."""

import json

import pytest

import tools.terminal as terminal
from tools.filesystem import replace_in_file, write_file


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(terminal, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(terminal, "WORKSPACE_DIR", tmp_path / "workspace")

    def no_confirmation(command, reason):
        raise AssertionError(f"não devia pedir confirmação: {command}")

    monkeypatch.setattr(terminal, "authorize", no_confirmation)

    folder = tmp_path / "workspace" / "bateria"
    folder.mkdir(parents=True)
    (folder / "servidor.log").write_text(
        "10:00 INFO iniciou\n10:05 ERRO disco cheio\n10:07 INFO ok\n10:09 ERRO rede caiu\n10:15 erro timeout\n", encoding="utf-8")
    (folder / "x.txt").write_text("15\n", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "y.txt").write_text("27\n", encoding="utf-8")

    return tmp_path


def run(command):
    return terminal.run_command(command, "teste")


# ---------------------------------------------------------
# Os comandos exatos que falharam no log
# ---------------------------------------------------------

def test_grep_count_from_the_log_now_answers_without_confirmation(project):
    result = run('grep -c "ERRO" workspace/bateria/servidor.log')

    assert result["success"] is True and result["stdout"] == "2" and result["harness_native"]


def test_dir_with_a_windows_path_from_the_log_lists_the_folder(project):
    result = run("dir workspace\\bateria")

    assert result["success"] is True
    assert "x.txt" in result["stdout"] and "sub/" in result["stdout"] and "servidor.log" in result["stdout"]


# ---------------------------------------------------------
# Listagem
# ---------------------------------------------------------

def test_ls_and_dir_default_to_the_project_root_and_support_recursion(project):
    assert "workspace/" in run("ls")["stdout"]
    assert "workspace/bateria/sub/y.txt" in run("dir /s workspace/bateria")["stdout"]
    assert "workspace/bateria/sub/y.txt" in run("ls -R workspace/bateria")["stdout"]


def test_harmless_listing_flags_are_accepted(project):
    assert run("ls -la workspace/bateria")["success"] is True
    assert run("dir /b workspace/bateria")["success"] is True


def test_a_leading_slash_path_means_the_project(project):
    assert "x.txt" in run("ls /workspace/bateria")["stdout"]


# ---------------------------------------------------------
# Busca
# ---------------------------------------------------------

def test_grep_variants(project):
    assert run("grep -ci erro workspace/bateria/servidor.log")["stdout"] == "3"
    assert "2:10:05 ERRO disco cheio" in run("grep -n ERRO workspace/bateria/servidor.log")["stdout"]
    assert run("grep -l 27 -r workspace/bateria")["stdout"] == "workspace/bateria/sub/y.txt"
    assert run("grep NAOEXISTE workspace/bateria/servidor.log")["stdout"] == "(nenhuma ocorrência)"


def test_grep_without_a_path_searches_the_whole_project(project):
    assert "workspace/bateria/servidor.log" in run("grep -l disco")["stdout"]


def test_findstr_variants(project):
    assert run('findstr /c:"ERRO" workspace/bateria/servidor.log').get("stdout").count("ERRO") == 2
    assert "erro timeout" in run("findstr /i erro workspace/bateria/servidor.log")["stdout"]


# ---------------------------------------------------------
# Leitura
# ---------------------------------------------------------

def test_type_and_cat_read_files(project):
    assert run("type workspace\\bateria\\x.txt")["stdout"].strip() == "15"
    assert run("cat workspace/bateria/x.txt workspace/bateria/sub/y.txt")["stdout"].split() == ["15", "27"]


# ---------------------------------------------------------
# O que continua passando pela confirmação
# ---------------------------------------------------------

@pytest.mark.parametrize("command", [
    "dir ..",
    "ls C:\\Windows",
    "grep -c ERRO ../fora.log",
    "grep -P ERRO workspace/bateria/servidor.log",
    "findstr /x ERRO workspace/bateria/servidor.log",
    "type C:\\Windows\\win.ini",
    "cat workspace/bateria/nao-existe.txt",
    'python -c "print(1)"',
])
def test_anything_outside_the_project_unknown_or_executable_still_asks(project, monkeypatch, command):
    asked = []
    monkeypatch.setattr(terminal, "authorize", lambda c, r: asked.append(c) or False)

    result = run(command)

    assert asked == [command] and result.get("cancelled") is True


# ---------------------------------------------------------
# replace_in_file e JSON
# ---------------------------------------------------------

def test_replace_in_a_missing_file_points_to_write_file(tmp_path):
    result = replace_in_file(str(tmp_path / "produto.txt"), "", "405")

    assert result["success"] is False and "write_file" in result["error"]


def test_empty_target_points_to_write_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")

    result = replace_in_file(str(target), "", "y")

    assert result["success"] is False and "write_file" in result["error"]


def test_invalid_json_is_refused_with_line_and_hint_and_the_file_is_kept(tmp_path):
    target = tmp_path / "tarefa.json"
    target.write_text('{"id": "ok"}', encoding="utf-8")

    result = write_file(str(target), '{"id": "x", "aceite": [1, 2,],}')

    assert result["success"] is False and "JSON inválido" in result["error"] and "linha 1" in result["error"]
    assert json.loads(target.read_text(encoding="utf-8")) == {"id": "ok"}


def test_valid_json_is_written(tmp_path):
    target = tmp_path / "tarefa.json"

    assert write_file(str(target), json.dumps({"id": "x", "aceite": []}))["success"] is True


def test_replace_that_would_break_a_json_file_is_refused(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"versao": 1, "nome": "teste"}', encoding="utf-8")

    result = replace_in_file(str(target), '"versao": 1,', '"versao": 2')

    assert result["success"] is False and "JSON inválido" in result["error"]
    assert '"versao": 1' in target.read_text(encoding="utf-8")


def test_other_file_types_are_not_validated_as_json(tmp_path):
    assert write_file(str(tmp_path / "nota.txt"), "{isso não é json")["success"] is True
