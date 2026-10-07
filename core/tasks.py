"""
Tarefas numeradas (tarefas/tarefa-NN-*.md) que o usuário chama por número.

    "dê continuidade à tarefa 2"   ou   "@tarefa2"

O Harness carrega o arquivo da tarefa, o pedido do usuário e o progresso salvo
em workspace/tarefa-NN/progresso.md, para o agente retomar de onde parou.
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

from core.paths import PROJECT_ROOT, TAREFAS_DIR, WORKSPACE_DIR

# Marca o início do prompt gerado; o agent.py usa isso para não confundir
# uma tarefa numerada com o fluxo de desenvolvimento do checklist.
TASK_MARKER = "[TAREFA "

MAX_PROGRESS_CHARS = 1500
MAX_ACCEPTANCE_OUTPUT_CHARS = 1500
ACCEPTANCE_TIMEOUT_SECONDS = 180

MARKER_PATTERN = re.compile(r"^\s*\[TAREFA (\d{2})\]")

# Só comandos pytest de aceite da própria tarefa, com poucas flags inofensivas.
ACCEPTANCE_PATTERN = re.compile(
    r"`pytest -m aceite (tests/test_aceite_tarefa\d{2}\.py)((?: -q| -x| -v)*)`"
)

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


def task_number_from_prompt(prompt: str) -> int | None:
    """Número da tarefa quando o prompt foi gerado por build_task_prompt; senão None."""

    match = MARKER_PATTERN.match(prompt or "")

    return int(match.group(1)) if match else None


def task_owner(number: int) -> str:
    """'usuario' (roteiro do usuário), 'agente' ou 'desconhecido', pela linha 'Quem faz:'."""

    path = find_task_file(number)

    if path is None:
        return "desconhecido"

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("quem faz:"):
            # Só vale o que vem antes do parêntese: "usuário (o agente só ajuda...)" é do usuário.
            owner = line.split(":", 1)[1].split("(")[0].lower()

            if "usuário" in owner or "usuario" in owner:
                return "usuario"

            if "agente" in owner:
                return "agente"

    return "desconhecido"


def acceptance_command(number: int) -> list[str] | None:
    """
    Comando do teste de aceite declarado em '## Pronto quando' (formato fixo
    `pytest -m aceite tests/test_aceite_tarefaNN.py -q`), pronto para subprocess; senão None.
    """

    path = find_task_file(number)

    if path is None:
        return None

    text = path.read_text(encoding="utf-8")

    if "## Pronto quando" not in text:
        return None

    section = text.split("## Pronto quando", 1)[1].split("\n## ", 1)[0]
    match = ACCEPTANCE_PATTERN.search(section)

    if not match:
        return None

    flags = match.group(2).split()

    return [sys.executable, "-m", "pytest", "-m", "aceite", match.group(1), *flags, "-p", "no:cacheprovider"]


def run_acceptance(command: list[str]) -> tuple[bool, str]:
    """Roda o teste de aceite. Retorna (passou, final da saída para mostrar ao modelo)."""

    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ACCEPTANCE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "O teste de aceite excedeu o tempo limite."
    except OSError as error:
        return False, f"Não foi possível rodar o teste de aceite: {error}"

    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

    if len(output) > MAX_ACCEPTANCE_OUTPUT_CHARS:
        output = "[...]\n" + output[-MAX_ACCEPTANCE_OUTPUT_CHARS:]

    return result.returncode == 0, output


def build_task_prompt(number: int, user_text: str) -> tuple[bool, str]:
    """Retorna (True, prompt completo) ou (False, mensagem de erro)."""

    path = find_task_file(number)

    if path is None:
        available = ", ".join(str(n) for n, _ in list_tasks()) or "nenhuma"
        return False, f"Tarefa {number} não encontrada. Tarefas disponíveis: {available}."

    if task_owner(number) == "usuario":
        return False, (
            f"A tarefa {number:02d} é SUA (não do agente): o roteiro está em {path.relative_to(PROJECT_ROOT)} "
            "e no ROTEIRO-DE-TESTES.md. O agente não a executa."
        )

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
