"""
Registra em specs/avaliacoes.md a tabela "FAST sozinho, FAST com think, SMART sozinho e cascata" a partir de uma
pasta de comparação (logs/comparacao/<data>). Pode receber várias pastas (por exemplo a noite FAST e a noite SMART).

    python scripts/registrar_avaliacoes.py logs/comparacao/20261012_210000 logs/comparacao/20261013_210000
    python scripts/registrar_avaliacoes.py            (usa as pastas mais recentes de logs/comparacao)
"""

import argparse
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import comparar_modelos as cmp  # noqa: E402

OUTPUT = ROOT / "specs" / "avaliacoes.md"
CATEGORY_BY_LABEL = {"9b-think": "FAST com think"}


def category(label: str) -> str:
    if label in CATEGORY_BY_LABEL:
        return CATEGORY_BY_LABEL[label]

    if label.startswith("par-"):
        return "Cascata (FAST + SMART)"

    if label.startswith("s-"):
        return "SMART sozinho"

    return "FAST sozinho"


def group_rate(results: list[dict], group: str) -> str:
    counted = [r for r in results if r.get("group") == group and not r.get("info") and not r.get("infra")]

    if not counted:
        return "-"

    return f"{sum(1 for r in counted if r.get('passed'))}/{len(counted)}"


def task3(results: list[dict]) -> str:
    runs = [r for r in results if r.get("id") == "tarefa3-informativo"]

    if not runs:
        return "-"

    return "passou" if any(r.get("passed") for r in runs) else "falhou"


def collect_all(folders: list[Path]) -> list[dict]:
    entries = []

    for folder in folders:
        for child in sorted(p for p in folder.iterdir() if p.is_dir()):
            entry = cmp.collect(child)

            if entry is not None:
                entries.append(entry)

    return entries


def build(entries: list[dict], sources: list[Path]) -> str:
    lines = [
        "# Avaliações registradas", "",
        f"Gerado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')} por `scripts/registrar_avaliacoes.py` a partir de: "
        + ", ".join(f"`{s.name}`" for s in sources) + ".", "",
        "Uma linha por perfil. \"Aprovação\" conta só os casos que valem nota (sem os informativos e sem falhas de infraestrutura).", "",
        "| Categoria | Perfil | Aprovação | Raciocínio | Tarefas reais | Tarefas numeradas | Tarefa 3 | tokens/s | VRAM pico (MB) | RAM livre mín. (MB) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = ["FAST sozinho", "FAST com think", "SMART sozinho", "Cascata (FAST + SMART)"]

    for entry in sorted(entries, key=lambda e: (order.index(category(e["label"])), e["label"])):
        summary = cmp.summarize_model(entry)
        results = entry["results"]
        consumption = entry.get("consumption") or {}
        rate = "NÃO RODOU" if entry.get("skipped") else f"{summary['passed']}/{summary['total']} ({summary['rate']}%)"
        speed = "-" if summary["avg_tok_s"] is None else summary["avg_tok_s"]
        lines.append(
            f"| {category(entry['label'])} | {entry['label']} | {rate} | {group_rate(results, 'raciocinio')} | {group_rate(results, 'real')} | "
            f"{group_rate(results, 'tarefas')} | {task3(results)} | {speed} | {consumption.get('vram_pico_mb') or '-'} | {consumption.get('ram_livre_min_mb') or '-'} |"
        )

    present = {category(e["label"]) for e in entries}
    missing = [c for c in order if c not in present]
    lines += ["", "Categorias sem dados nesta rodada: " + (", ".join(missing) if missing else "nenhuma (as quatro foram medidas)."), ""]

    return "\n".join(lines)


def latest_folders(count: int = 2) -> list[Path]:
    base = ROOT / "logs" / "comparacao"

    if not base.exists():
        return []

    return sorted((p for p in base.iterdir() if p.is_dir()), reverse=True)[:count]


def main(argv=None) -> int:
    from core.console import ensure_utf8_console

    ensure_utf8_console()

    parser = argparse.ArgumentParser(description="Registra as avaliações em specs/avaliacoes.md")
    parser.add_argument("pastas", nargs="*", help="pastas de logs/comparacao (padrão: as duas mais recentes)")
    parser.add_argument("--saida", default=str(OUTPUT))
    args = parser.parse_args(argv)

    folders = [Path(p) for p in args.pastas] or latest_folders()
    entries = collect_all([f for f in folders if f.is_dir()])

    if not entries:
        print("Não encontrei resultados de comparação. Rode o comparar.bat antes.")
        return 1

    text = build(entries, folders)
    Path(args.saida).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nSalvo em {args.saida}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
