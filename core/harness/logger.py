from datetime import datetime
from pathlib import Path


LOG_DIR = Path.home() / "local-agent" / "logs"
LOG_FILE = LOG_DIR / "agent.log"


def log(event: str, details: str = ""):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{timestamp}] {event}"

    if details:
        line += f" | {details}"

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")

    print(line)
