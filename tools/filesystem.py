from pathlib import Path

from core.paths import PROJECT_ROOT, TMP_ROOT, WORKSPACE_DIR


WORKSPACE = WORKSPACE_DIR.resolve()
PROTECTED_SUBDIRS = [
    (PROJECT_ROOT / ".git").resolve(),
    (PROJECT_ROOT / ".venv").resolve(),
]


def is_path_writable(target: Path) -> tuple[bool, str]:
    """
    Verifica se um caminho está dentro dos diretórios autorizados para escrita:
    - Raiz do projeto, exceto .git e .venv
    - diretório temporário do sistema
    """
    target = target.resolve()

    for protected in PROTECTED_SUBDIRS:
        try:
            target.relative_to(protected)
            return (
                False,
                f"Escrita proibida dentro de diretório protegido do sistema/ambiente: {protected.name}",
            )
        except ValueError:
            pass

    in_project = False
    try:
        target.relative_to(PROJECT_ROOT)
        in_project = True
    except ValueError:
        pass

    in_tmp = False
    try:
        target.relative_to(TMP_ROOT)
        in_tmp = True
    except ValueError:
        pass

    if not (in_project or in_tmp):
        return (
            False,
            f"Escrita permitida somente dentro do projeto ({PROJECT_ROOT}) ou {TMP_ROOT}",
        )

    return True, ""


def list_directory(path: str) -> dict:
    target = Path(path).expanduser().resolve()

    if not target.exists():
        return {
            "success": False,
            "error": f"Diretório não encontrado: {target}",
        }

    if not target.is_dir():
        return {
            "success": False,
            "error": f"Não é um diretório: {target}",
        }

    items = []

    for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
        items.append({
            "name": item.name,
            "type": "directory" if item.is_dir() else "file",
        })

    return {
        "success": True,
        "path": str(target),
        "items": items,
    }


def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    target = Path(path).expanduser().resolve()

    if not target.exists():
        return {
            "success": False,
            "error": f"Arquivo não encontrado: {target}",
        }

    if not target.is_file():
        return {
            "success": False,
            "error": f"Não é um arquivo: {target}",
        }

    try:
        content = target.read_text(encoding="utf-8")
        lines = content.splitlines()
        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = max(1, int(start_line)) if start_line is not None else 1
            end = min(total_lines, int(end_line)) if end_line is not None else total_lines

            if start > end:
                return {
                    "success": False,
                    "error": f"start_line ({start}) não pode ser maior que end_line ({end}).",
                }

            selected = lines[start - 1 : end]
            formatted = [f"{i}: {line}" for i, line in enumerate(selected, start=start)]

            return {
                "success": True,
                "path": str(target),
                "total_lines": total_lines,
                "start_line": start,
                "end_line": end,
                "content": "\n".join(formatted),
            }

        return {
            "success": True,
            "path": str(target),
            "total_lines": total_lines,
            "content": content,
        }

    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "Arquivo não parece ser texto UTF-8",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def write_file(path: str, content: str) -> dict:
    target = Path(path).expanduser().resolve()

    writable, error_msg = is_path_writable(target)
    if not writable:
        return {
            "success": False,
            "error": error_msg,
        }

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def replace_in_file(path: str, target: str, replacement: str) -> dict:
    """
    Substitui um trecho exato de texto dentro de um arquivo existente.
    Exige que o trecho alvo ocorra exatamente uma vez para evitar substituições acidentais.
    """
    target_file = Path(path).expanduser().resolve()

    if not target_file.exists():
        return {
            "success": False,
            "error": f"Arquivo não encontrado: {target_file}",
        }

    if not target_file.is_file():
        return {
            "success": False,
            "error": f"Não é um arquivo: {target_file}",
        }

    writable, error_msg = is_path_writable(target_file)
    if not writable:
        return {
            "success": False,
            "error": error_msg,
        }

    if not target:
        return {
            "success": False,
            "error": "O trecho alvo (target) não pode ser vazio.",
        }

    try:
        content = target_file.read_text(encoding="utf-8")

        count = content.count(target)
        if count == 0:
            return {
                "success": False,
                "error": "O trecho alvo (target) não foi encontrado no arquivo.",
            }

        if count > 1:
            return {
                "success": False,
                "error": (
                    f"O trecho alvo aparece {count} vezes no arquivo. "
                    "Forneça mais linhas de contexto para torná-lo único."
                ),
            }

        new_content = content.replace(target, replacement, 1)
        target_file.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "path": str(target_file),
            "target_length": len(target),
            "replacement_length": len(replacement),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
