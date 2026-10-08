"""
Compara modelos FAST rodando a MESMA bateria de testes em cada um.

    python scripts/comparar_modelos.py                       (qwen3:8b, qwen3.5:9b e qwen3.5:4b)
    python scripts/comparar_modelos.py --base logs/bateria/<pasta>   (reaproveita a rodada que você já fez com o qwen3:8b)
    python scripts/comparar_modelos.py --rapido              (bateria curta em cada modelo)
    python scripts/comparar_modelos.py --modelos qwen3.5:9b,gemma4:12b
    python scripts/comparar_modelos.py --montar logs/comparacao/<pasta>   (só refaz o COMPARATIVO.md)

O modelo é trocado só durante cada execução (variável LOCALAGENT_FAST_MODEL); o registry e o
resto do projeto não mudam. Tudo fica em logs/comparacao/<data>/ e o resultado em COMPARATIVO.md.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_MODELS = ["qwen3:8b", "qwen3.5:9b", "qwen3.5:4b"]
BASE_LABEL = "qwen3:8b"
APPROX_DOWNLOAD_GB = {"qwen3:8b": 5.2, "qwen3.5:9b": 7.0, "qwen3.5:4b": 3.5}
MIN_ACCEPTABLE_TOK_S = 15
SMOKE_TIMEOUT_SECONDS = 180
MODEL_TIME_LIMIT_SECONDS = 6000
UNLOAD_WAIT_SECONDS = 40

PING_TOOL = {
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Responde pong.",
        "parameters": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]},
    },
}


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")


# ---------------------------------------------------------
# Verificações de ambiente (injetáveis nos testes)
# ---------------------------------------------------------

def run_cmd(args: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return done.returncode, (done.stdout + done.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def model_installed(model: str) -> bool:
    code, _ = run_cmd(["ollama", "show", model])
    return code == 0


def pull_model(model: str) -> bool:
    return subprocess.run(["ollama", "pull", model]).returncode == 0


def stop_model(model: str) -> None:
    run_cmd(["ollama", "stop", model])


def smoke_test(model: str) -> dict:
    """Uma chamada real: o modelo responde, aceita `think=False` e sabe pedir uma ferramenta?"""

    import ollama

    client = ollama.Client(host="http://localhost:11434", timeout=SMOKE_TIMEOUT_SECONDS)
    started = time.monotonic()

    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": "Use a ferramenta ping com o texto 'oi'."}],
            tools=[PING_TOOL],
            think=False,
            options={"num_ctx": 8192},
        )
    except Exception as exc:  # noqa: BLE001 - qualquer erro do servidor deve virar motivo no relatório
        return {"ok": False, "tool_call": False, "seconds": round(time.monotonic() - started, 1), "error": str(exc)[:200]}

    calls = getattr(response.message, "tool_calls", None) or []

    return {"ok": True, "tool_call": bool(calls), "seconds": round(time.monotonic() - started, 1), "error": ""}


# ---------------------------------------------------------
# Leitura e comparação
# ---------------------------------------------------------

def collect(folder: Path, label: str | None = None) -> dict | None:
    """Lê uma pasta de bateria (resultados.json e, se houver, meta.json)."""

    results_file = folder / "resultados.json"

    if not results_file.exists():
        return None

    try:
        results = json.loads(results_file.read_text(encoding="utf-8"))
        meta_file = folder / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    except (OSError, ValueError):
        return None

    if not isinstance(results, list):
        return None

    return {"label": label or meta.get("model") or folder.name, "results": results, "meta": meta}


def summarize_model(entry: dict) -> dict:
    results = entry["results"]
    counted = [r for r in results if not r.get("info") and not r.get("infra")]
    infra = sum(1 for r in results if r.get("infra") and not r.get("passed"))
    passed = sum(1 for r in counted if r["passed"])
    speeds = [r["tok_s"] for r in results if r.get("tok_s")]
    events: dict[str, int] = {}

    for r in results:
        for name, count in r.get("events", {}).items():
            events[name] = events.get(name, 0) + count

    seconds = [r["seconds"] for r in results]
    groups: dict[str, list[int]] = {}

    for r in counted:
        bucket = groups.setdefault(r["group"], [0, 0])
        bucket[0] += 1 if r["passed"] else 0
        bucket[1] += 1

    return {
        "label": entry["label"],
        "passed": passed,
        "total": len(counted),
        "rate": round(100 * passed / len(counted)) if counted else 0,
        "minutes": round(sum(seconds) / 60, 1),
        "avg_seconds": round(sum(seconds) / len(seconds), 1) if seconds else 0,
        "avg_tok_s": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "tokens_in": sum(r.get("tokens_in", 0) for r in results) if any("tokens_in" in r for r in results) else None,
        "tokens_out": sum(r.get("tokens_out", 0) for r in results) if any("tokens_in" in r for r in results) else None,
        "calls": sum(r.get("model_calls", 0) for r in results),
        "tools": sum(r["tools"] for r in results),
        "failed_tools": sum(r["failed_tools"] for r in results),
        "violations": sum(1 for r in results if r.get("violations")),
        "infra": infra,
        "events": events,
        "groups": {name: tuple(values) for name, values in groups.items()},
        "ollama_ps": entry["meta"].get("ollama_ps", "n/d"),
        "smoke": entry.get("smoke"),
        "skipped": entry.get("skipped", ""),
    }


def case_cells(entries: list[dict]) -> dict[str, dict[str, str]]:
    """caso -> {modelo: 'passou/total'} (INFO quando o caso é só informativo)."""

    table: dict[str, dict[str, str]] = {}

    for entry in entries:
        by_case: dict[str, list[dict]] = {}

        for r in entry["results"]:
            by_case.setdefault(r["id"], []).append(r)

        for case_id, runs in by_case.items():
            if all(r.get("info") for r in runs):
                cell = "info: " + ("passou" if all(r["passed"] for r in runs) else "falhou") + f" ({runs[0]['status']})"
            else:
                cell = f"{sum(1 for r in runs if r['passed'])}/{len(runs)}"

            table.setdefault(case_id, {})[entry["label"]] = cell

    return table


def cli_table(summaries: list[dict]) -> str:
    """Tabela de texto puro para o terminal: um modelo por linha, os números que importam."""

    headers = ["Modelo", "Casos ok", "%", "Casos falhos", "Erros de ferramenta", "Tokens entrada", "Tokens saída", "tok/s", "Minutos", "Falhas Ollama"]
    rows = []

    for s in summaries:
        if s["skipped"]:
            rows.append([s["label"], "NÃO RODOU", "-", "-", "-", "-", "-", "-", "-", "-"])
            continue

        def number(value):
            return "n/d" if value is None else f"{value:,}".replace(",", ".")

        rows.append([
            s["label"], f"{s['passed']}/{s['total']}", f"{s['rate']}%", str(s["total"] - s["passed"]), str(s["failed_tools"]),
            number(s["tokens_in"]), number(s["tokens_out"]), "n/d" if s["avg_tok_s"] is None else str(s["avg_tok_s"]), str(s["minutes"]), str(s["infra"]),
        ])

    widths = [max(len(row[i]) for row in [headers] + rows) for i in range(len(headers))]

    def line(cells):
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    separator = "-+-".join("-" * width for width in widths)

    return "\n".join([line(headers), separator] + [line(row) for row in rows])


def build_comparison(entries: list[dict], date: str) -> str:
    runnable = [e for e in entries if e.get("results")]
    summaries = [summarize_model(e) for e in entries]
    lines = ["# Comparativo de modelos FAST", "", f"- Data: {date}", f"- Modelos: {', '.join(e['label'] for e in entries)}", "",
             "## Visão geral", "", "```", cli_table(summaries), "```", ""]

    lines += ["## Resumo", "",
              "| Modelo | Aprovação | Tempo total (min) | s/caso | tokens/s | Ferramentas (falhas) | Violações | Chamou ferramenta no teste rápido |",
              "|---|---|---|---|---|---|---|---|"]

    for s in summaries:
        if s["skipped"]:
            lines.append(f"| {s['label']} | NÃO RODOU | - | - | - | - | - | {s['skipped'][:80]} |")
            continue

        smoke = s["smoke"]
        smoke_text = "n/d" if smoke is None else ("sim" if smoke["tool_call"] else "NÃO")
        speed = "n/d" if s["avg_tok_s"] is None else s["avg_tok_s"]
        lines.append(
            f"| {s['label']} | {s['passed']}/{s['total']} ({s['rate']}%) | {s['minutes']} | {s['avg_seconds']} | {speed} "
            f"| {s['tools']} ({s['failed_tools']}) | {s['violations']} | {smoke_text} |"
        )

    group_names = list(dict.fromkeys(g for s in summaries for g in s["groups"]))
    lines += ["", "## Por grupo (passou/total)", "", "| Grupo | " + " | ".join(s["label"] for s in summaries) + " |",
              "|---|" + "---|" * len(summaries)]

    for group in group_names:
        cells = [f"{s['groups'][group][0]}/{s['groups'][group][1]}" if group in s["groups"] else "-" for s in summaries]
        lines.append(f"| {group} | " + " | ".join(cells) + " |")

    matrix = case_cells(runnable)
    labels = [s["label"] for s in summaries]
    lines += ["", "## Caso a caso", "", "| Caso | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]

    for case_id, cells in matrix.items():
        lines.append(f"| {case_id} | " + " | ".join(cells.get(label, "-") for label in labels) + " |")

    event_names = sorted({name for s in summaries for name in s["events"]})
    lines += ["", "## Eventos do Harness (soma)", ""]

    if event_names:
        lines += ["| Evento | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
        for name in event_names:
            lines.append(f"| {name} | " + " | ".join(str(s["events"].get(name, 0)) for s in summaries) + " |")
    else:
        lines.append("- nenhum")

    lines += ["", "## Cabe na placa? (`ollama ps` logo após o primeiro caso)", ""]

    for s in summaries:
        lines += [f"**{s['label']}**", "", "```", s["ollama_ps"], "```", ""]

    lines += ["## Como ler", "",
              "- Escolha o modelo com **maior aprovação** nos casos que contam (os `info` não entram).",
              f"- **Descarte** quem tiver violação de arquivo protegido, quem ficar abaixo de {MIN_ACCEPTABLE_TOK_S} tokens/s ou quem aparecer com CPU no `ollama ps` (sinal de que não coube na GPU).",
              "- Em empate, fica o mais rápido (menor `s/caso`).",
              "- Uma diferença de 1 ou 2 casos pode ser sorte do modelo; vale mais olhar o grupo `seguranca` e `tarefas`.", ""]

    return "\n".join(lines)


# ---------------------------------------------------------
# Execução
# ---------------------------------------------------------

def confirm_downloads(missing: list[str], assume_yes: bool) -> bool:
    if not missing:
        return True

    total = sum(APPROX_DOWNLOAD_GB.get(m, 0) for m in missing)
    print("Faltam estes modelos no Ollama:")

    for model in missing:
        size = APPROX_DOWNLOAD_GB.get(model)
        print(f"  - {model}" + (f" (cerca de {size} GB)" if size else ""))

    print(f"Download total estimado: {total:.1f} GB.")

    if assume_yes:
        return True

    try:
        return input("Baixar agora? (S/N): ").strip().lower().startswith("s")
    except (EOFError, OSError):
        return False


def wait_unloaded(model: str, seconds: int = UNLOAD_WAIT_SECONDS) -> bool:
    """Espera o modelo sair da memória (dois modelos juntos não cabem nos 8 GB e vazariam para a CPU)."""

    deadline = time.time() + seconds

    while time.time() < deadline:
        _, listing = run_cmd(["ollama", "ps"])

        if model.lower() not in listing.lower():
            return True

        time.sleep(2)

    return False


def run_one(model: str, folder: Path, args, resume: bool = False) -> bool:
    """Roda a bateria de um modelo. Devolve False se estourou o tempo (os resultados parciais ficam em disco)."""

    command = [sys.executable, str(ROOT / "scripts" / "bateria.py"), "--saida", str(folder), "--repeticoes", str(args.repeticoes)]

    if args.rapido:
        command.append("--rapido")

    if resume:
        command.append("--retomar")

    env = {**os.environ, "LOCALAGENT_FAST_MODEL": model, "PYTHONUTF8": "1"}
    finished = True

    try:
        subprocess.run(command, env=env, cwd=str(ROOT), stdin=subprocess.DEVNULL, timeout=args.limite_modelo)
    except subprocess.TimeoutExpired:
        finished = False
        print(f"\n!!! {model} passou de {args.limite_modelo // 60} min e foi interrompido; os resultados parciais foram mantidos.")
    except OSError as exc:
        finished = False
        print(f"\n!!! Não consegui rodar a bateria de {model}: {exc}")

    stop_model(model)

    if not wait_unloaded(model):
        print(f"Aviso: {model} ainda aparece carregado; o próximo modelo pode usar CPU.")

    return finished


def write_partial(entries: list[dict], root: Path) -> None:
    """Grava o COMPARATIVO.md com o que já existe, depois de cada modelo (uma queda não perde nada)."""

    try:
        report = build_comparison(entries, datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
        (root / "COMPARATIVO.md").write_text(report, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"(não consegui atualizar o COMPARATIVO.md parcial: {exc})")


def orchestrate(args) -> int:
    from bateria import ensure_ollama, keep_awake
    from core.console import ensure_utf8_console

    ensure_utf8_console()

    models = [m.strip() for m in args.modelos.split(",") if m.strip()]
    entries: list[dict] = []

    if args.base:
        base = collect(Path(args.base), args.base_nome)

        if base is None:
            print(f"Não encontrei resultados.json em {args.base}")
            return 1

        entries.append(base)
        models = [m for m in models if m != args.base_nome]

    code, version = run_cmd(["ollama", "--version"])

    if code != 0:
        print("O Ollama não respondeu. Abra o Ollama e rode de novo.")
        return 1

    resume = bool(args.retomar)
    missing = [m for m in models if not model_installed(m)]

    if not confirm_downloads(missing, args.sim):
        print("Sem baixar os modelos não dá para comparar. Rode de novo e responda S, ou use --modelos com o que já tem.")
        return 1

    for model in missing:
        if not pull_model(model):
            print(f"Não consegui baixar {model}; ele será pulado.")

    root = Path(args.retomar) if resume else ROOT / "logs" / "comparacao" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    print(f"\nComparação em: {root}\nOllama: {version.splitlines()[-1]}\n")

    try:
        with keep_awake():
            for model in models:
                try:
                    run_model(model, root, args, entries, resume, ensure_ollama)
                except Exception as exc:  # noqa: BLE001 - um modelo com problema não pode derrubar os outros
                    print(f"!!! Erro inesperado com {model}: {type(exc).__name__}: {exc}")
                    entries.append({"label": model, "results": [], "meta": {}, "skipped": f"erro inesperado: {exc}"})

                write_partial(entries, root)
    except KeyboardInterrupt:
        print("\nInterrompido. Gerando o comparativo do que foi feito.")

    return finish(entries, root)


def run_model(model: str, root: Path, args, entries: list[dict], resume: bool, ensure) -> None:
    folder = root / slug(model)

    if resume and (folder / "meta.json").exists():
        done = collect(folder, model)

        if done is not None:
            print(f"=== {model}: já concluído numa rodada anterior, aproveitando ===")
            entries.append(done)
            return

    print(f"=== {model}: teste rápido ===")

    if not model_installed(model):
        entries.append({"label": model, "results": [], "meta": {}, "skipped": "não está instalado"})
        return

    if not ensure():
        entries.append({"label": model, "results": [], "meta": {}, "skipped": "Ollama indisponível"})
        return

    smoke = smoke_test(model)
    print(f"    respondeu: {'sim' if smoke['ok'] else 'NÃO'} | chamou ferramenta: {'sim' if smoke['tool_call'] else 'NÃO'} | {smoke['seconds']} s {smoke['error']}")

    if not smoke["ok"]:
        entries.append({"label": model, "results": [], "meta": {}, "smoke": smoke, "skipped": "incompatível: " + smoke["error"]})
        return

    print(f"=== {model}: bateria completa ===")
    run_one(model, folder, args, resume=resume and (folder / "resultados.json").exists())
    entry = collect(folder, model)

    if entry is None:
        entries.append({"label": model, "results": [], "meta": {}, "smoke": smoke, "skipped": "a bateria não gerou resultados"})
    else:
        entry["smoke"] = smoke
        entries.append(entry)


def finish(entries: list[dict], root: Path) -> int:
    report = build_comparison(entries, datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    (root / "COMPARATIVO.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print("\nVISÃO GERAL\n" + cli_table([summarize_model(e) for e in entries]))
    print(f"\nTraga de volta a pasta inteira: {root}\n(e o arquivo logs\\agent.log)")
    return 0


def rebuild(folder: Path) -> int:
    entries = []

    for child in sorted(p for p in folder.iterdir() if p.is_dir()):
        entry = collect(child)

        if entry:
            entries.append(entry)

    if not entries:
        print(f"Nenhuma bateria encontrada em {folder}")
        return 1

    return finish(entries, folder)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compara modelos FAST com a mesma bateria")
    parser.add_argument("--modelos", default=",".join(DEFAULT_MODELS), help="modelos separados por vírgula")
    parser.add_argument("--base", help="pasta de uma bateria já feita (reaproveitada como coluna do modelo base)")
    parser.add_argument("--base-nome", default=BASE_LABEL, help="nome do modelo da rodada --base")
    parser.add_argument("--rapido", action="store_true", help="bateria curta em cada modelo")
    parser.add_argument("--repeticoes", type=int, default=2)
    parser.add_argument("--sim", action="store_true", help="baixa os modelos que faltam sem perguntar")
    parser.add_argument("--montar", help="refaz o COMPARATIVO.md de uma pasta de comparação")
    parser.add_argument("--retomar", help="continua uma comparação interrompida (pasta em logs/comparacao): aproveita modelos concluídos e o que já rodou")
    parser.add_argument("--limite-modelo", type=int, default=MODEL_TIME_LIMIT_SECONDS, help="segundos máximos por modelo (padrão 6000)")
    args = parser.parse_args(argv)

    if args.montar:
        return rebuild(Path(args.montar))

    return orchestrate(args)


if __name__ == "__main__":
    sys.exit(main())
