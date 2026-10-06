import uuid
from datetime import datetime

from core.console import safe_print
from core.paths import LOGS_DIR


LOG_DIR = LOGS_DIR
LOG_FILE = LOG_DIR / "agent.log"

_run_id = "-"


def new_run_id() -> str:
    """Inicia um novo run e devolve seu id (8 caracteres)."""

    global _run_id

    _run_id = uuid.uuid4().hex[:8]

    return _run_id


def get_run_id() -> str:
    return _run_id


def log(event: str, details: str = ""):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{timestamp}] [{_run_id}] {event}"

    if details:
        line += f" | {details}"

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")

    safe_print(line)
