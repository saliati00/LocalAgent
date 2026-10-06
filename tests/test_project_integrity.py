import py_compile
from pathlib import Path

from core.paths import PROJECT_ROOT

SKIP_DIRS = {".venv", ".git", "__pycache__", "skills_pending", "workspace"}


def test_every_python_file_compiles():
    """Pega erros de sintaxe em arquivos que nenhum teste importa (ex.: o bloco __main__ do agent.py)."""

    failures = []

    for path in PROJECT_ROOT.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(PROJECT_ROOT).parts):
            continue

        try:
            py_compile.compile(str(path), doraise=True, cfile=str(Path("nul")) if False else None)
        except py_compile.PyCompileError as error:
            failures.append(f"{path.relative_to(PROJECT_ROOT)}: {error.msg}")

    assert not failures, "\n".join(failures)
