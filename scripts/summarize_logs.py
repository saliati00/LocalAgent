"""
Resume logs/agent.log: tamanho do prompt, tokens, avisos de contexto, escaladas e paradas.

    python scripts/summarize_logs.py            (usa logs/agent.log)
    python scripts/summarize_logs.py caminho\\do\\log
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

LOG_LINE = re.compile(r"^\[[^\]]+\] (?:\[([^\]]+)\] )?(\w+)(?: \| (.*))?$")
TOKENS = re.compile(r"input=(\d+) \| output=(\d+)")

EVENTS_OF_INTEREST = (
    "CONTEXT_NEAR_LIMIT",
    "CONTEXT_TRUNCATED",
    "TOOL_CACHE_HIT",
    "ESCALATE_TO_SMART",
    "SMART_UNAVAILABLE",
    "DE_ESCALATE",
    "NEEDS_HUMAN",
    "LOOP_BLOCKED",
    "STAGNATION_THRESHOLD_REACHED",
    "CANCELLED",
    "DONE",
)


def summarize(lines: list[str]) -> dict:
    events: Counter = Counter()
    inputs: list[int] = []
    outputs: list[int] = []
    prompt_totals: list[int] = []
    sections: dict[str, list[int]] = {}
    runs: set[str] = set()

    for line in lines:
        match = LOG_LINE.match(line.rstrip("\n"))

        if not match:
            continue

        run_id, event, details = match.group(1), match.group(2), match.group(3) or ""

        if run_id and run_id != "-":
            runs.add(run_id)

        events[event] += 1

        if event == "TOKENS":
            found = TOKENS.search(details)
            if found:
                inputs.append(int(found.group(1)))
                outputs.append(int(found.group(2)))

        if event == "PROMPT_SIZES":
            try:
                report = json.loads(details)
            except ValueError:
                continue

            for name, values in report.items():
                if isinstance(values, dict) and "est_tokens" in values:
                    sections.setdefault(name, []).append(values["est_tokens"])

            total = report.get("_total", {}).get("est_tokens")
            if total is not None:
                prompt_totals.append(total)

    real_inputs = [value for value in inputs if value > 50]

    return {
        "runs": len(runs),
        "model_calls": len(inputs),
        "input_tokens": _stats(real_inputs),
        "output_tokens": _stats(outputs),
        "prompt_estimate_tokens": _stats(prompt_totals),
        "prompt_sections_avg_tokens": {
            name: round(sum(values) / len(values)) for name, values in sections.items()
        },
        "events": {name: events[name] for name in EVENTS_OF_INTEREST if events[name]},
    }


def _stats(values: list[int]) -> dict:
    if not values:
        return {}

    return {
        "count": len(values),
        "avg": round(sum(values) / len(values)),
        "max": max(values),
    }


def print_report(report: dict) -> None:
    print("RESUMO DO LOG")
    print(f"- execuções (run_id): {report['runs']}")
    print(f"- chamadas ao modelo: {report['model_calls']}")

    for label, key in (
        ("tokens de entrada", "input_tokens"),
        ("tokens de saída", "output_tokens"),
        ("prompt estimado (PROMPT_SIZES)", "prompt_estimate_tokens"),
    ):
        stats = report[key]
        if stats:
            print(f"- {label}: média {stats['avg']}, máximo {stats['max']} ({stats['count']} medições)")

    if report["prompt_sections_avg_tokens"]:
        print("- tokens médios por seção do prompt:")
        for name, value in sorted(report["prompt_sections_avg_tokens"].items(), key=lambda item: -item[1]):
            print(f"    {name}: {value}")

    if report["events"]:
        print("- eventos:")
        for name, count in report["events"].items():
            print(f"    {name}: {count}")

    print("")
    print("Atenção: CONTEXT_TRUNCATED/CONTEXT_NEAR_LIMIT altos significam que a janela está pequena demais.")


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "logs" / "agent.log"

    if not path.exists():
        print(f"Log não encontrado: {path}")
        return 1

    print_report(summarize(path.read_text(encoding="utf-8", errors="replace").splitlines()))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
