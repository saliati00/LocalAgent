import os
import re
import shutil

from core.paths import VENV_BIN_DIR


MAX_TOOLS = 30
NAME_PATTERN = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


def check_tools(names: list) -> dict:
    """
    Verifica, em uma única chamada, quais executáveis existem no PATH
    (incluindo o .venv do projeto). Somente leitura.

    Substitui dezenas de chamadas 'command -v X' / 'where X'.
    """

    if not isinstance(names, list) or not names:
        return {
            "success": False,
            "error": "Informe uma lista não vazia de nomes de ferramentas.",
        }

    if len(names) > MAX_TOOLS:
        return {
            "success": False,
            "error": f"No máximo {MAX_TOOLS} ferramentas por chamada.",
        }

    invalid = [n for n in names if not isinstance(n, str) or not NAME_PATTERN.match(n)]

    if invalid:
        return {
            "success": False,
            "error": f"Nomes inválidos (use apenas letras, números, '.', '_', '+', '-'): {invalid}",
        }

    search_path = str(VENV_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

    tools = {}

    for name in names:
        found = shutil.which(name, path=search_path)
        tools[name] = {"found": found is not None, "path": found}

    return {
        "success": True,
        "tools": tools,
        "found": [n for n in names if tools[n]["found"]],
        "missing": [n for n in names if not tools[n]["found"]],
    }
