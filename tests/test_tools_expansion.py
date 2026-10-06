import pytest
from pathlib import Path

from tools.filesystem import (
    read_file,
    write_file,
    replace_in_file,
    PROJECT_ROOT,
)
from tools.manager import (
    validate_arguments,
    execute_tool,
)
from tools.web import web_search, fetch_url


def test_write_file_allowed_in_project(tmp_path):
    test_file = PROJECT_ROOT / "workspace" / "test_unit_write.txt"
    try:
        result = write_file(str(test_file), "conteudo de teste")
        assert result["success"] is True
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "conteudo de teste"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_write_file_blocked_in_protected_dirs():
    git_file = PROJECT_ROOT / ".git" / "fake_file.txt"
    result = write_file(str(git_file), "tentativa maliciosa")
    assert result["success"] is False
    assert "proibida" in result["error"].lower()

    venv_file = PROJECT_ROOT / ".venv" / "fake_file.txt"
    result_venv = write_file(str(venv_file), "tentativa maliciosa")
    assert result_venv["success"] is False
    assert "proibida" in result_venv["error"].lower()


def test_write_file_blocked_outside_project():
    forbidden_file = "/etc/test_unauthorized.txt"
    result = write_file(forbidden_file, "conteudo")
    assert result["success"] is False
    assert "permitida somente dentro do projeto" in result["error"]


def test_read_file_line_range(tmp_path):
    test_file = PROJECT_ROOT / "workspace" / "test_range.txt"
    lines = ["linha 1", "linha 2", "linha 3", "linha 4", "linha 5"]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    try:
        result = read_file(str(test_file), start_line=2, end_line=4)
        assert result["success"] is True
        assert result["total_lines"] == 5
        assert result["start_line"] == 2
        assert result["end_line"] == 4
        assert "2: linha 2" in result["content"]
        assert "4: linha 4" in result["content"]
        assert "1: linha 1" not in result["content"]
        assert "5: linha 5" not in result["content"]
    finally:
        if test_file.exists():
            test_file.unlink()


def test_read_file_invalid_range(tmp_path):
    test_file = PROJECT_ROOT / "workspace" / "test_invalid_range.txt"
    test_file.write_text("linha 1\nlinha 2", encoding="utf-8")
    try:
        result = read_file(str(test_file), start_line=5, end_line=2)
        assert result["success"] is False
        assert "não pode ser maior" in result["error"]
    finally:
        if test_file.exists():
            test_file.unlink()


def test_replace_in_file_success():
    test_file = PROJECT_ROOT / "workspace" / "test_replace.txt"
    test_file.write_text("prefixo\nalvo_aqui\nsufixo", encoding="utf-8")
    try:
        result = replace_in_file(str(test_file), "alvo_aqui", "substituido_com_sucesso")
        assert result["success"] is True
        content = test_file.read_text(encoding="utf-8")
        assert "substituido_com_sucesso" in content
        assert "alvo_aqui" not in content
    finally:
        if test_file.exists():
            test_file.unlink()


def test_replace_in_file_target_not_found():
    test_file = PROJECT_ROOT / "workspace" / "test_replace_nf.txt"
    test_file.write_text("texto qualquer", encoding="utf-8")
    try:
        result = replace_in_file(str(test_file), "inexistente", "novo")
        assert result["success"] is False
        assert "não foi encontrado" in result["error"]
    finally:
        if test_file.exists():
            test_file.unlink()


def test_replace_in_file_ambiguous_target():
    test_file = PROJECT_ROOT / "workspace" / "test_replace_amb.txt"
    test_file.write_text("duplicado\nmeio\nduplicado", encoding="utf-8")
    try:
        result = replace_in_file(str(test_file), "duplicado", "novo")
        assert result["success"] is False
        assert "aparece 2 vezes" in result["error"]
    finally:
        if test_file.exists():
            test_file.unlink()


def test_validation_new_tools():
    # replace_in_file
    valid, error = validate_arguments("replace_in_file", {
        "path": "arquivo.txt",
        "target": "antigo",
        "replacement": "novo",
    })
    assert valid is True

    # web_search
    valid, error = validate_arguments("web_search", {
        "query": "fedora linux",
    })
    assert valid is True

    # fetch_url
    valid, error = validate_arguments("fetch_url", {
        "url": "https://example.com",
    })
    assert valid is True


def test_web_search_empty():
    result = web_search("")
    assert result["success"] is False
    assert "vazia" in result["error"]


def test_fetch_url_empty():
    result = fetch_url("")
    assert result["success"] is False
    assert "não fornecida" in result["error"]


def test_memory_tools_execution(tmp_path, monkeypatch):
    import tools.manager as manager
    from core.memory.store import MemoryStore
    from tools.manager import execute_tool

    # Isola do memory/store.json real do projeto.
    monkeypatch.setattr(manager, "_memory_store", MemoryStore(str(tmp_path / "store.json")))

    # Save
    res_save = execute_tool("save_memory", {
        "category": "notes",
        "key": "test_key",
        "value": "valor_de_teste",
        "description": "desc",
    })
    assert res_save["success"] is True

    # Get single key
    res_get = execute_tool("get_memory", {
        "category": "notes",
        "key": "test_key",
    })
    assert res_get["success"] is True
    assert res_get["found"] is True
    assert res_get["value"] == "valor_de_teste"

    # Get missing key
    res_missing = execute_tool("get_memory", {
        "category": "notes",
        "key": "non_existent_key",
    })
    assert res_missing["success"] is True
    assert res_missing["found"] is False
    assert res_missing["value"] is None

    # Get entire category
    res_cat = execute_tool("get_memory", {
        "category": "notes",
    })
    assert res_cat["success"] is True
    assert "test_key" in res_cat["entries"]


def test_memory_tools_validation():
    # Valid save
    valid, err = validate_arguments("save_memory", {
        "category": "environment",
        "key": "tool",
        "value": "path",
    })
    assert valid is True

    # Missing required argument
    valid_inv, err_inv = validate_arguments("save_memory", {
        "category": "environment",
    })
    assert valid_inv is False

