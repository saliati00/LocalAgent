"""Busca de texto e de nomes de arquivo dentro do projeto (somente leitura)."""

import fnmatch
import os
from pathlib import Path

from core.paths import PROJECT_ROOT

MAX_RESULTS_LIMIT = 50
DEFAULT_MAX_RESULTS = 30
MAX_LINE_CHARS = 160
MAX_FILE_BYTES = 1_000_000
MAX_FILES_SCANNED = 5000

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "logs", "backups", ".pytest_cache"}


def _resolve_inside_project(path: str) -> Path | None:
    base = (PROJECT_ROOT / (path or ".")).resolve()

    try:
        base.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None

    return base


def _is_binary(sample: bytes) -> bool:
    return b"\x00" in sample


def search_files(
    pattern: str = "",
    path: str = ".",
    glob: str = "*",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict:
    """
    Procura `pattern` (texto, sem diferenciar maiúsculas) nas linhas dos arquivos que casam com `glob`.
    Sem `pattern`, lista os arquivos que casam com `glob` (busca por nome).
    A busca fica restrita ao projeto e devolve no máximo `max_results` resultados curtos.
    """

    base = _resolve_inside_project(path)

    if base is None:
        return {"success": False, "error": "A busca só pode ocorrer dentro da pasta do projeto."}

    if not base.exists():
        return {"success": False, "error": f"Caminho não encontrado: {path}"}

    try:
        limit = max(1, min(int(max_results), MAX_RESULTS_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_RESULTS

    needle = (pattern or "").strip().lower()
    glob = glob or "*"

    matches: list[dict] = []
    files_scanned = 0
    truncated = False

    candidates = [base] if base.is_file() else None

    def walk():
        if candidates is not None:
            yield from candidates
            return

        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)

            for name in sorted(files):
                yield Path(root) / name

    for file_path in walk():
        if not fnmatch.fnmatch(file_path.name.lower(), glob.lower()):
            continue

        files_scanned += 1

        if files_scanned > MAX_FILES_SCANNED:
            truncated = True
            break

        relative = str(file_path.relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")

        if not needle:
            matches.append({"file": relative})

            if len(matches) >= limit:
                truncated = True
                break

            continue

        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                continue

            with file_path.open("rb") as handle:
                if _is_binary(handle.read(2048)):
                    continue

            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for number, line in enumerate(text.splitlines(), start=1):
            if needle in line.lower():
                snippet = " ".join(line.split())

                if len(snippet) > MAX_LINE_CHARS:
                    snippet = snippet[: MAX_LINE_CHARS - 3] + "..."

                matches.append({"file": relative, "line": number, "text": snippet})

                if len(matches) >= limit:
                    truncated = True
                    break

        if truncated:
            break

    result = {
        "success": True,
        "matches": matches,
        "total_shown": len(matches),
        "files_scanned": min(files_scanned, MAX_FILES_SCANNED),
    }

    if truncated:
        result["truncated"] = True
        result["notice"] = "Há mais resultados. Refine o padrão, a pasta (path) ou o filtro de nome (glob)."

    return result
