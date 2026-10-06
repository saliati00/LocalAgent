"""Prompts salvos em prompts/*.md, para iniciar tarefas com um comando curto (@nome)."""

import re

from core.paths import PROMPTS_DIR

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def list_prompts() -> list[str]:
    if not PROMPTS_DIR.exists():
        return []

    return sorted(path.stem for path in PROMPTS_DIR.glob("*.md"))


def load_prompt(name: str) -> tuple[bool, str]:
    """Retorna (True, texto) ou (False, mensagem de erro)."""

    name = (name or "").strip()

    if not NAME_PATTERN.match(name):
        return False, f"Nome de prompt inválido: '{name}'."

    path = PROMPTS_DIR / f"{name}.md"

    if not path.exists():
        available = ", ".join(f"@{n}" for n in list_prompts()) or "nenhum"
        return False, f"Prompt '{name}' não encontrado. Disponíveis: {available}."

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        return False, f"O prompt '{name}' está vazio."

    return True, text
