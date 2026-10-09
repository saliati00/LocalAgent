"""
Confere e pontua tarefas de avaliação (sem chamar nenhum modelo).

    python scripts/eval/runner.py                       confere as tarefas de scripts/eval/tarefas contra o estado atual do projeto
    python scripts/eval/runner.py --resultados r.json   resume uma lista de resultados [{"task_id": "...", "passed": true}, ...]

Formato das tarefas: veja scripts/eval/FORMATO.md.
"""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = Path(__file__).resolve().parent / "tarefas"
COMMAND_TIMEOUT_SECONDS = 60


def load_tasks(directory) -> list[dict]:
    """Lê os arquivos *.json da pasta, em ordem alfabética."""

    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(directory).glob("*.json"))]


def safe_path(workdir: Path, relative) -> Path | None:
    """Caminho dentro de workdir; None se for vazio, absoluto, com unidade (C:) ou com '..'."""

    if not isinstance(relative, str) or not relative.strip():
        return None

    if relative.startswith(("/", "\\")) or ":" in relative:
        return None

    parts = relative.replace("\\", "/").split("/")

    if ".." in parts:
        return None

    target = (Path(workdir) / relative).resolve()
    base = Path(workdir).resolve()

    return target if target == base or base in target.parents else None


def _check_one(criterion: dict, workdir: Path) -> str | None:
    """Mensagem de erro se o critério falhar; None se passar."""

    kind = criterion.get("type")

    if kind in ("file_exists", "file_contains"):
        target = safe_path(workdir, criterion.get("path"))

        if target is None:
            return f"caminho inválido ou fora da pasta de trabalho: {criterion.get('path')!r}"

        if not target.is_file():
            return f"arquivo não existe: {criterion['path']}"

        if kind == "file_contains":
            text = criterion.get("text")

            if not isinstance(text, str):
                return f"critério file_contains sem 'text': {criterion['path']}"

            if text not in target.read_text(encoding="utf-8", errors="replace"):
                return f"{criterion['path']} não contém {text!r}"

        return None

    if kind == "command_exit_zero":
        command = criterion.get("command")

        if not isinstance(command, str) or not command.strip():
            return "critério command_exit_zero sem 'command'"

        try:
            arguments = shlex.split(command)
            done = subprocess.run(arguments, cwd=str(workdir), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=COMMAND_TIMEOUT_SECONDS, shell=False)
        except subprocess.TimeoutExpired:
            return f"o comando passou de {COMMAND_TIMEOUT_SECONDS} s: {command}"
        except (OSError, ValueError) as exc:
            return f"não consegui rodar o comando ({exc}): {command}"

        if done.returncode != 0:
            tail = (done.stdout + done.stderr).strip()[-160:]
            return f"o comando terminou com código {done.returncode}: {command}" + (f" | {tail}" if tail else "")

        return None

    return f"tipo de critério desconhecido: {kind!r}"


def check_acceptance(criteria, workdir) -> tuple[bool, list[str]]:
    """True se TODOS os critérios passam. Lista com uma mensagem por critério que falhou."""

    if not criteria:
        return False, ["a tarefa não tem critérios de aceite (lista vazia não conta como sucesso)"]

    errors = []

    for criterion in criteria:
        message = _check_one(criterion, Path(workdir)) if isinstance(criterion, dict) else f"critério inválido: {criterion!r}"

        if message:
            errors.append(message)

    return not errors, errors


def summarize(results) -> dict:
    """total, passou, taxa (0 a 1) e, por tarefa, quantas rodadas e quantas passaram."""

    by_task: dict[str, dict] = {}

    for result in results:
        entry = by_task.setdefault(result["task_id"], {"runs": 0, "passed": 0})
        entry["runs"] += 1
        entry["passed"] += 1 if result.get("passed") else 0

    total = sum(entry["runs"] for entry in by_task.values())
    passed = sum(entry["passed"] for entry in by_task.values())

    return {"total": total, "passed": passed, "pass_rate": (passed / total) if total else 0, "by_task": by_task}


def evaluate_directory(tasks_dir, workdir) -> list[dict]:
    """Confere o aceite de cada tarefa contra o estado atual do projeto (útil depois de o agente trabalhar)."""

    results = []

    for task in load_tasks(tasks_dir):
        passed, errors = check_acceptance(task.get("aceite", []), workdir)
        results.append({"task_id": task.get("id", "?"), "passed": passed, "errors": errors})

    return results


def print_report(results) -> dict:
    summary = summarize(results)

    for task_id, entry in summary["by_task"].items():
        print(f"- {task_id}: {entry['passed']}/{entry['runs']}")

    print(f"Taxa de sucesso: {summary['passed']}/{summary['total']} ({round(100 * summary['pass_rate'])}%)")

    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Confere e pontua tarefas de avaliação")
    parser.add_argument("--tarefas", default=str(TASKS_DIR), help="pasta com as tarefas .json")
    parser.add_argument("--pasta-de-trabalho", default=str(PROJECT_ROOT), help="pasta onde os critérios são conferidos")
    parser.add_argument("--resultados", help="arquivo .json com resultados já prontos para resumir")
    args = parser.parse_args(argv)

    if args.resultados:
        results = json.loads(Path(args.resultados).read_text(encoding="utf-8"))
    else:
        results = evaluate_directory(args.tarefas, args.pasta_de_trabalho)

        for result in results:
            for error in result["errors"]:
                print(f"  [{result['task_id']}] {error}")

    print_report(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
