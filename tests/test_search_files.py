import pytest

import tools.search as search
from tools.manager import execute_tool


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".git").mkdir()
    (root / "__pycache__").mkdir()

    (root / "src" / "a.py").write_text("def soma(a, b):\n    return a + b\n# TODO: Somar mais\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("print('oi')\n", encoding="utf-8")
    (root / "docs" / "leia.md").write_text("Use a função soma para somar.\n", encoding="utf-8")
    (root / ".git" / "config").write_text("soma escondida\n", encoding="utf-8")
    (root / "__pycache__" / "x.py").write_text("soma em cache\n", encoding="utf-8")
    (root / "binario.bin").write_bytes(b"soma\x00\x01\x02")

    monkeypatch.setattr(search, "PROJECT_ROOT", root)

    return root


def found(result):
    return {(m["file"], m.get("line")) for m in result["matches"]}


def test_text_search_returns_file_line_and_snippet_ignoring_case(project):
    result = search.search_files("SOMA")

    assert result["success"] is True
    assert ("src/a.py", 1) in found(result)
    assert ("docs/leia.md", 1) in found(result)
    assert any("def soma" in m["text"] for m in result["matches"])


def test_glob_filters_by_file_name(project):
    result = search.search_files("soma", glob="*.py")

    assert {m["file"] for m in result["matches"]} == {"src/a.py"}


def test_without_pattern_it_lists_files_by_name(project):
    result = search.search_files(glob="*.py")

    assert {m["file"] for m in result["matches"]} == {"src/a.py", "src/b.py"}
    assert all("line" not in m for m in result["matches"])


def test_skips_git_cache_and_binary_files(project):
    result = search.search_files("soma")

    files = {m["file"] for m in result["matches"]}

    assert ".git/config" not in files
    assert "__pycache__/x.py" not in files
    assert "binario.bin" not in files


def test_results_are_capped_and_flagged(project):
    (project / "muitos.txt").write_text("\n".join("alvo linha" for _ in range(100)), encoding="utf-8")

    result = search.search_files("alvo", max_results=5)

    assert result["total_shown"] == 5
    assert result["truncated"] is True
    assert "Refine" in result["notice"]

    assert search.search_files("alvo", max_results=9999)["total_shown"] == search.MAX_RESULTS_LIMIT


def test_long_lines_are_shortened(project):
    (project / "longa.txt").write_text("alvo " + "x" * 500, encoding="utf-8")

    match = search.search_files("alvo", glob="longa.txt")["matches"][0]

    assert len(match["text"]) <= search.MAX_LINE_CHARS


def test_can_search_a_subfolder_or_a_single_file(project):
    assert {m["file"] for m in search.search_files("soma", path="docs")["matches"]} == {"docs/leia.md"}
    assert {m["file"] for m in search.search_files("soma", path="src/a.py")["matches"]} == {"src/a.py"}


@pytest.mark.parametrize("path", ["..", "../fora", "C:\\Windows", "/etc"])
def test_cannot_search_outside_the_project(project, path):
    result = search.search_files("soma", path=path)

    assert result["success"] is False


def test_missing_path_is_an_error(project):
    assert search.search_files("soma", path="nao_existe")["success"] is False


def test_available_through_the_tool_manager():
    result = execute_tool("search_files", {"pattern": "def search_files", "glob": "search.py"})

    assert result["success"] is True
    assert any(m["file"].endswith("tools/search.py") for m in result["matches"])


def test_search_results_are_memoized_and_invalidated_by_writes():
    from core.harness.memo import ToolMemo

    memo = ToolMemo()
    memo.record("search_files", {"pattern": "x"}, {"success": True, "matches": []})
    assert memo.lookup("search_files", {"pattern": "x"})["cached"] is True

    memo.record("write_file", {"path": "a", "content": "b"}, {"success": True})
    assert memo.lookup("search_files", {"pattern": "x"}) is None
