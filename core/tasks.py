"""
Tarefas numeradas (tarefas/tarefa-NN-*.md) que o usuário chama por número.

    "dê continuidade à tarefa 2"   ou   "@tarefa2"

O Harness carrega o arquivo da tarefa, o pedido do usuário e o progresso salvo
em workspace/tarefa-NN/progresso.md, para o agente retomar de onde parou.
"""

import re
from pathlib import Path

from core.paths import TAREFAS_DIR, WORKSPACE_DIR

# Marca o início do prompt gerado; o agent.py usa isso para não confundir
# uma tarefa numerada com o fluxo de desenvolvimento do checklist.
TASK_MARKER = "[TAREFA "

MAX_PROGRESS_CHARS = 1500

DIRECT_REFERENCE = re.compile(r"^\s*@tarefa\s*-?\s*0*(\d{1,2})\b", re.IGNORECASE)

VERB_REFERENCE = re.compile(
    r"\b(continu\w*|retom\w*|execut\w*|inici\w*|segu\w*|fa[çc]a|fazer|rode|d[êe])\b"
    r".{0,30}?\btarefa\s*-?\s*0*(\d{1,2})\b",
    re.IGNORECASE,
)


def find_task_number(text: str) -> int | None:
    """Número da tarefa citado como '@tarefa2' ou 'dê continuidade à tarefa 2'; senão None."""

    text = text or ""

    match = DIRECT_REFERENCE.match(text)
    if match:
        return int(match.group(1))

    match = VERB_REFERENCE.search(text)
    if match:
        return int(match.group(2))

    return None


def find_task_file(number: int) -> Path | None:
    if not TAREFAS_DIR.exists():
        return None

    matches = sorted(TAREFAS_DIR.glob(f"tarefa-{number:02d}-*.md"))

    return matches[0] if matches else None


def list_tasks() -> list[tuple[int, str]]:
    """[(número, nome do arquivo)] das tarefas existentes."""

    if not TAREFAS_DIR.exists():
        return []

    found = []

    for path in sorted(TAREFAS_DIR.glob("tarefa-*.md")):
        match = re.match(r"tarefa-(\d+)-", path.name)
        if match:
            found.append((int(match.group(1)), path.name))

    return found


def progress_file(number: int) -> Path:
    return WORKSPACE_DIR / f"tarefa-{number:02d}" / "progresso.md"


def read_progress(number: int) -> str:
    """Final do arquivo de progresso (o mais recente), ou '' se não existir."""

    path = progress_file(number)

    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8").strip()

    if len(text) > MAX_PROGRESS_CHARS:
        text = "[...início omitido...]\n" + text[-MAX_PROGRESS_CHARS:]

    return text


def build_task_prompt(number: int, user_text: str) -> tuple[bool, str]:
    """Retorna (True, prompt completo) ou (False, mensagem de erro)."""

    path = find_task_file(number)

    if path is None:
        available = ", ".join(str(n) for n, _ in list_tasks()) or "nenhuma"
        return False, f"Tarefa {number} não encontrada. Tarefas disponíveis: {available}."

    body = path.read_text(encoding="utf-8").strip()
    progress = read_progress(number)

    progress_block = (
        f"PROGRESSO JÁ SALVO (continue a partir daqui, não refaça):\n{progress}"
        if progress
        else "PROGRESSO JÁ SALVO: nenhum. Comece pelo passo 1."
    )

    prompt = (
        f"{TASK_MARKER}{number:02d}]\n"
        f"{body}\n\n"
        f"PEDIDO DO USUÁRIO: {(user_text or '').strip()}\n\n"
        f"{progress_block}"
    )

    return True, prompt
