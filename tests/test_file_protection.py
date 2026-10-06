import os
from pathlib import Path

import pytest

from core.paths import PROJECT_ROOT, TMP_ROOT
from tools.filesystem import is_path_writable, replace_in_file, write_file


PROTECTED = [
    "specs/projeto.md",
    "models/registry.json",
    "memory/store.json",
    "core/harness/permissions.py",
    "core/harness/new_module.py",
    "core/paths.py",
    "tools/terminal.py",
    "tools/filesystem.py",
    "tests/test_memory.py",
    "tests/new_test.py",
    "agent.py",
    ".git/config",
    ".venv/pyvenv.cfg",
    "skills/windows/SKILL.md",
    "skills/nova/SKILL.md",
    "skills_pending/nova/SKILL.md",
    "prompts/iniciar-desenvolvimento.md",
    "prompts/novo.md",
]


@pytest.mark.parametrize("relative", PROTECTED)
def test_protected_paths_are_not_writable(relative):
    writable, error = is_path_writable(PROJECT_ROOT / relative)
    assert writable is False
    assert error


def test_write_file_to_spec_is_denied_and_does_not_change_it():
    spec = PROJECT_ROOT / "specs" / "projeto.md"
    before = spec.read_bytes()

    result = write_file(str(spec), "sobrescrito")

    assert result["success"] is False
    assert spec.read_bytes() == before


def test_replace_in_file_on_protected_path_is_denied():
    result = replace_in_file(str(PROJECT_ROOT / "core" / "harness" / "permissions.py"), "import", "xx")
    assert result["success"] is False


@pytest.mark.parametrize("relative", [
    "workspace/novo.txt",
    "benchmarks/resultado.json",
    "tools/plugins/novo.py",
])
def test_regular_project_paths_remain_writable(relative):
    writable, error = is_path_writable(PROJECT_ROOT / relative)
    assert writable is True, error


def test_temp_dir_is_writable():
    writable, _ = is_path_writable(TMP_ROOT / "qualquer.txt")
    assert writable is True


def test_outside_project_is_denied():
    # Raiz da unidade: fora do projeto e fora da pasta temporária, onde quer que o
    # repositório esteja (um clone dentro de %TEMP% não pode mudar o resultado).
    outside = Path(PROJECT_ROOT.anchor) / "fora-do-projeto-localagent.txt"
    writable, _ = is_path_writable(outside)
    assert writable is False


@pytest.mark.skipif(os.name != "nt", reason="Windows é case-insensitive")
def test_protection_ignores_case_on_windows():
    writable, _ = is_path_writable(PROJECT_ROOT / "SPECS" / "PROJETO.MD")
    assert writable is False
