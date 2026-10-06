from tools.environment import MAX_TOOLS, check_tools
from tools.manager import execute_tool


def test_check_tools_finds_python_and_reports_missing():
    result = check_tools(["python", "ferramenta-que-nao-existe-xyz"])

    assert result["success"] is True
    assert result["tools"]["python"]["found"] is True
    assert result["tools"]["python"]["path"]
    assert result["found"] == ["python"]
    assert result["missing"] == ["ferramenta-que-nao-existe-xyz"]


def test_check_tools_rejects_bad_input():
    assert check_tools([])["success"] is False
    assert check_tools("git")["success"] is False
    assert check_tools(["git; rm -rf"])["success"] is False
    assert check_tools(["a"] * (MAX_TOOLS + 1))["success"] is False


def test_check_tools_runs_through_the_tool_manager():
    result = execute_tool("check_tools", {"names": ["python"]})
    assert result["success"] is True
