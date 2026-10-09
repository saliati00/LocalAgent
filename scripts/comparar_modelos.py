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
import contextlib
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
DEFAULT_URL = "http://localhost:11434"
VARIANT_PORT = 11435
VARIANT_WAIT_SECONDS = 90

# Cache de KV quantizado (metade da memória do cache): variáveis do SERVIDOR do Ollama.
KV8 = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}

# Perfis = modelo + janela de contexto + configuração do servidor. Os que mudam o servidor rodam num
# servidor próprio (porta 11435), sem mexer no Ollama normal do usuário.
PROFILES = {
    "9b": {"model": "qwen3.5:9b", "num_ctx": 8192, "server": {}},
    "4b": {"model": "qwen3.5:4b", "num_ctx": 8192, "server": {}},
    "9b-kv8": {"model": "qwen3.5:9b", "num_ctx": 8192, "server": KV8},
    "4b-16k-kv8": {"model": "qwen3.5:4b", "num_ctx": 16384, "server": KV8},
    "8b": {"model": "qwen3:8b", "num_ctx": 8192, "server": {}},
}
FAST_PROFILES = ["9b", "4b", "9b-kv8", "4b-16k-kv8", "8b"]

# Candidatos a SMART. Rodam só os grupos difíceis (raciocínio, tarefas reais, tarefas numeradas), uma rodada
# cada, com mais tempo por caso e por chamada (parte do modelo fica na CPU). O que importa é acertar, não a velocidade.
SMART_BASE = {
    "num_ctx": 8192, "server": KV8, "role": "smart", "grupos": "raciocinio,real,tarefas", "repeticoes": 1,
    "timeout_factor": 3, "call_timeout": 600, "limite": 10800,
}
PROFILES.update({
    "s-gemma12": {"model": "gemma4:12b", **SMART_BASE},
    "s-gptoss20": {"model": "gpt-oss:20b", **SMART_BASE},
    # Pareamento: o FAST (9b) tenta e, travado, entrega ao SMART com o resumo de passagem (handover).
    "par-9b+gemma12": {"model": "qwen3.5:9b", "smart_model": "gemma4:12b", **{**SMART_BASE, "grupos": "real,tarefas"}},
    "s-coder30": {"model": "qwen3-coder:30b", **SMART_BASE},
})
SMART_PROFILES = ["s-gemma12", "s-gptoss20", "par-9b+gemma12", "s-coder30"]
DEFAULT_PROFILES = FAST_PROFILES + SMART_PROFILES
PROFILE_GROUPS = {"fast": FAST_PROFILES, "smart": SMART_PROFILES, "tudo": DEFAULT_PROFILES}

APPROX_DOWNLOAD_GB = {"qwen3:8b": 5.2, "qwen3.5:9b": 7.0, "qwen3.5:4b": 3.5, "gemma4:12b": 8.0, "gpt-oss:20b": 14.0, "qwen3-coder:30b": 19.0}
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


def profile_from_model(model: str) -> dict:
    return {"label": model, "model": model, "num_ctx": 8192, "server": {}}


def resolve_profiles(args) -> list[dict]:
    """--modelos (lista de modelos, config padrão) tem prioridade; senão --perfis; senão os perfis padrão."""

    if getattr(args, "modelos", ""):
        return [profile_from_model(m.strip()) for m in args.modelos.split(",") if m.strip()]

    names = []

    for name in [n.strip() for n in (getattr(args, "perfis", "") or "tudo").split(",") if n.strip()]:
        names += PROFILE_GROUPS.get(name, [name])

    names = list(dict.fromkeys(names))
    unknown = [n for n in names if n not in PROFILES]

    if unknown:
        raise SystemExit(f"Perfis desconhecidos: {', '.join(unknown)}. Disponíveis: {', '.join(PROFILES)}; grupos: {', '.join(PROFILE_GROUPS)}.")

    return [{"label": name, **PROFILES[name]} for name in names]


def host_of(url: str) -> str:
    return url.split("://", 1)[-1]


# ---------------------------------------------------------
# Verificações de ambiente (injetáveis nos testes)
# ---------------------------------------------------------

def run_cmd(args: list[str], timeout: int = 60, env: dict | None = None) -> tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return done.returncode, (done.stdout + done.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def model_installed(model: str) -> bool:
    code, _ = run_cmd(["ollama", "show", model])
    return code == 0


def pull_model(model: str) -> bool:
    return subprocess.run(["ollama", "pull", model]).returncode == 0


def server_env(url: str) -> dict:
    """Ambiente para os comandos `ollama ...` falarem com o servidor certo."""

    return {**os.environ, "OLLAMA_HOST": host_of(url)}


def stop_model(model: str, url: str = DEFAULT_URL) -> None:
    run_cmd(["ollama", "stop", model], env=server_env(url))


def smoke_test(model: str, url: str = DEFAULT_URL, num_ctx: int = 8192) -> dict:
    """Uma chamada real: o modelo responde, aceita `think=False` e sabe pedir uma ferramenta?"""

    import ollama

    client = ollama.Client(host=url, timeout=SMOKE_TIMEOUT_SECONDS)
    started = time.monotonic()

    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": "Use a ferramenta ping com o texto 'oi'."}],
            tools=[PING_TOOL],
            think=False,
            options={"num_ctx": num_ctx},
        )
    except Exception as exc:  # noqa: BLE001 - qualquer erro do servidor deve virar motivo no relatório
        return {"ok": False, "tool_call": False, "seconds": round(time.monotonic() - started, 1), "error": str(exc)[:200]}

    calls = getattr(response.message, "tool_calls", None) or []

    return {"ok": True, "tool_call": bool(calls), "seconds": round(time.monotonic() - started, 1), "error": ""}


@contextlib.contextmanager
def server_for(profile: dict, folder: Path):
    """
    Servidor do perfil. Sem configuração especial, é o Ollama normal. Com ela (por exemplo cache de KV
    quantizado), sobe um servidor próprio na porta 11435, usa os mesmos modelos já baixados e o encerra no fim.
    """

    if not profile.get("server"):
        yield DEFAULT_URL
        return

    from bateria import ollama_alive

    url = f"http://127.0.0.1:{VARIANT_PORT}"
    env = {**os.environ, **profile["server"], "OLLAMA_HOST": host_of(url)}
    folder.mkdir(parents=True, exist_ok=True)
    log = open(folder / "servidor-ollama.log", "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    try:
        process = subprocess.Popen(["ollama", "serve"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags)
    except OSError as exc:
        log.close()
        raise RuntimeError(f"não consegui iniciar o servidor do perfil: {exc}") from exc

    try:
        deadline = time.time() + VARIANT_WAIT_SECONDS

        while time.time() < deadline and not ollama_alive(url=url):
            if process.poll() is not None:
                raise RuntimeError("o servidor do perfil encerrou ao iniciar (ver servidor-ollama.log)")

            time.sleep(2)

        if not ollama_alive(url=url):
            raise RuntimeError("o servidor do perfil não respondeu a tempo")

        yield url
    finally:
        process.terminate()

        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()

        log.close()


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

    profiled = [e for e in entries if e.get("profile")]

    if profiled:
        lines += ["", "## Perfis testados", "", "| Perfil | Papel | Modelo (SMART) | Contexto | Servidor | Grupos |", "|---|---|---|---|---|---|"]

        for e in profiled:
            p = e["profile"]
            server = ", ".join(f"{k}={v}" for k, v in p.get("server", {}).items()) or "padrão"
            model = p["model"] + (f" (SMART: {p['smart_model']})" if p.get("smart_model") else "")
            lines.append(f"| {e['label']} | {p.get('role', 'fast')} | {model} | {p['num_ctx']} | {server} | {p.get('grupos') or 'todos'} |")

    lines += ["", "## Cabe na placa? (`ollama ps` logo após o primeiro caso)", ""]

    for s in summaries:
        lines += [f"**{s['label']}**", "", "```", s["ollama_ps"], "```", ""]

    if any(e.get("profile", {}).get("role") == "smart" for e in entries):
        lines += ["## Escolhendo o SMART", "",
                  "- Os perfis `s-*` rodam só os grupos difíceis (raciocínio, tarefas reais e tarefas numeradas), uma rodada cada. Compare **entre eles** e com o melhor FAST nos mesmos grupos, não pela nota total.",
                  "- O que decide: passar nas **tarefas reais** e na **tarefa 3** (casos `info`, veja a coluna de cada perfil em \"Caso a caso\"). Um SMART que não passa onde o FAST falha não serve.",
                  "- A velocidade pesa pouco (ele só entra quando o FAST trava): 3 tokens/s ou mais é aceitável; CPU no `ollama ps` é esperado nos modelos grandes.",
                  "- O perfil `par-*` testa o conjunto: veja `ESCALATE_TO_SMART` e `SMART_AVAILABLE` nos eventos. Se o FAST escalou e o caso passou, o pareamento funcionou.",
                  ""]

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


def wait_unloaded(model: str, seconds: int = UNLOAD_WAIT_SECONDS, url: str = DEFAULT_URL) -> bool:
    """Espera o modelo sair da memória (dois modelos juntos não cabem nos 8 GB e vazariam para a CPU)."""

    deadline = time.time() + seconds

    while time.time() < deadline:
        _, listing = run_cmd(["ollama", "ps"], env=server_env(url))

        if model.lower() not in listing.lower():
            return True

        time.sleep(2)

    return False


def run_one(profile: dict, folder: Path, args, resume: bool = False, url: str = DEFAULT_URL) -> bool:
    """Roda a bateria de um perfil. Devolve False se estourou o tempo (os resultados parciais ficam em disco)."""

    command = [sys.executable, str(ROOT / "scripts" / "bateria.py"), "--saida", str(folder),
               "--repeticoes", str(profile.get("repeticoes", args.repeticoes))]

    if args.rapido:
        command.append("--rapido")

    if profile.get("grupos"):
        command += ["--grupos", profile["grupos"]]

    if resume:
        command.append("--retomar")

    env = {
        **os.environ, **profile.get("server", {}),
        "LOCALAGENT_FAST_MODEL": profile["model"], "LOCALAGENT_NUM_CTX": str(profile.get("num_ctx", 8192)),
        "LOCALAGENT_OLLAMA_URL": url, "OLLAMA_HOST": host_of(url), "PYTHONUTF8": "1",
    }

    if profile.get("smart_model"):
        env["LOCALAGENT_SMART_MODEL"] = profile["smart_model"]

    if profile.get("timeout_factor"):
        env["LOCALAGENT_TIMEOUT_FACTOR"] = str(profile["timeout_factor"])

    if profile.get("call_timeout"):
        env["LOCALAGENT_CALL_TIMEOUT"] = str(profile["call_timeout"])

    limit = int(profile.get("limite", args.limite_modelo))
    finished = True

    try:
        subprocess.run(command, env=env, cwd=str(ROOT), stdin=subprocess.DEVNULL, timeout=limit)
    except subprocess.TimeoutExpired:
        finished = False
        print(f"\n!!! {profile['label']} passou de {limit // 60} min e foi interrompido; os resultados parciais foram mantidos.")
    except OSError as exc:
        finished = False
        print(f"\n!!! Não consegui rodar a bateria de {profile['label']}: {exc}")

    for loaded in dict.fromkeys([profile["model"], profile.get("smart_model")]):
        if not loaded:
            continue

        stop_model(loaded, url)

        if not wait_unloaded(loaded, url=url):
            print(f"Aviso: {loaded} ainda aparece carregado; o próximo perfil pode usar CPU.")

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

    profiles = resolve_profiles(args)
    entries: list[dict] = []

    if args.base:
        base = collect(Path(args.base), args.base_nome)

        if base is None:
            print(f"Não encontrei resultados.json em {args.base}")
            return 1

        entries.append(base)
        profiles = [p for p in profiles if p["label"] != args.base_nome]

    code, version = run_cmd(["ollama", "--version"])

    if code != 0:
        print("O Ollama não respondeu. Abra o Ollama e rode de novo.")
        return 1

    resume = bool(args.retomar)
    models = list(dict.fromkeys(m for p in profiles for m in (p["model"], p.get("smart_model")) if m))
    missing = [m for m in models if not model_installed(m)]

    if not confirm_downloads(missing, args.sim):
        print("Sem baixar os modelos não dá para comparar. Rode de novo e responda S, ou use --modelos com o que já tem.")
        return 1

    for model in missing:
        if not pull_model(model):
            print(f"Não consegui baixar {model}; os perfis dele serão pulados.")

    root = Path(args.retomar) if resume else ROOT / "logs" / "comparacao" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    print(f"\nComparação em: {root}\nOllama: {version.splitlines()[-1]}\nPerfis: {', '.join(p['label'] for p in profiles)}\n")

    try:
        with keep_awake():
            for profile in profiles:
                try:
                    run_model(profile, root, args, entries, resume, ensure_ollama)
                except Exception as exc:  # noqa: BLE001 - um perfil com problema não pode derrubar os outros
                    print(f"!!! Erro inesperado com {profile['label']}: {type(exc).__name__}: {exc}")
                    entries.append({"label": profile["label"], "results": [], "meta": {}, "profile": profile, "skipped": f"erro inesperado: {exc}"})

                write_partial(entries, root)
    except KeyboardInterrupt:
        print("\nInterrompido. Gerando o comparativo do que foi feito.")

    return finish(entries, root)


def run_model(profile: dict, root: Path, args, entries: list[dict], resume: bool, ensure) -> None:
    if isinstance(profile, str):
        profile = profile_from_model(profile)

    label, model = profile["label"], profile["model"]
    folder = root / slug(label)

    if resume and (folder / "meta.json").exists():
        done = collect(folder, label)

        if done is not None:
            print(f"=== {label}: já concluído numa rodada anterior, aproveitando ===")
            done["profile"] = profile
            entries.append(done)
            return

    print(f"=== {label} ({model}, contexto {profile.get('num_ctx', 8192)}"
          + (", servidor próprio" if profile.get("server") else "") + "): teste rápido ===")

    if not model_installed(model):
        entries.append({"label": label, "results": [], "meta": {}, "profile": profile, "skipped": "não está instalado"})
        return

    if not profile.get("server") and not ensure():
        entries.append({"label": label, "results": [], "meta": {}, "profile": profile, "skipped": "Ollama indisponível"})
        return

    try:
        with server_for(profile, folder) as url:
            smoke = smoke_test(model, url, profile.get("num_ctx", 8192))
            print(f"    respondeu: {'sim' if smoke['ok'] else 'NÃO'} | chamou ferramenta: {'sim' if smoke['tool_call'] else 'NÃO'} | {smoke['seconds']} s {smoke['error']}")

            if not smoke["ok"]:
                entries.append({"label": label, "results": [], "meta": {}, "profile": profile, "smoke": smoke, "skipped": "incompatível: " + smoke["error"]})
                return

            print(f"=== {label}: bateria completa ===")
            run_one(profile, folder, args, resume=resume and (folder / "resultados.json").exists(), url=url)
    except RuntimeError as exc:
        entries.append({"label": label, "results": [], "meta": {}, "profile": profile, "skipped": str(exc)})
        return

    entry = collect(folder, label)

    if entry is None:
        entries.append({"label": label, "results": [], "meta": {}, "profile": profile, "smoke": smoke, "skipped": "a bateria não gerou resultados"})
    else:
        entry.update(smoke=smoke, profile=profile)
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
    parser.add_argument("--perfis", default="", help="perfis ou grupos (fast, smart, tudo) separados por vírgula (padrão: tudo = " + ",".join(DEFAULT_PROFILES) + ")")
    parser.add_argument("--modelos", default="", help="em vez de perfis: modelos separados por vírgula, com a configuração padrão")
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
