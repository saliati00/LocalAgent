"""
Estimativa de ordem de grandeza: cada modelo CABE na sua máquina? A que velocidade deve gerar?

    python scripts/estimar_desempenho.py
    python scripts/estimar_desempenho.py --ctx 16384 --kv8
    python scripts/estimar_desempenho.py --ram 32 --vram 12 --cpu-bw 60

O modelo de cálculo (simples de propósito):

  1. MEMÓRIA: pesos + cache de KV (cresce linearmente com o contexto) + uma folga. O que não cabe na VRAM
     vai para a RAM (o Ollama divide por camadas); se nem a RAM aguenta, o Windows pagina em disco,
     que é onde o PC trava.
  2. VELOCIDADE: gerar um token exige LER da memória os pesos ativos. Então
         tempo por token = (bytes na GPU / banda da GPU) + (bytes na CPU / banda da RAM)
     (modelos MoE leem só os especialistas ativos). A banda real é uma fração da teórica (eficiência).

Limites (leia antes de confiar): é uma ficha de bolso, não um benchmark. Os números de arquitetura (cache de
KV por mil tokens, parâmetros ativos) são palpites de família. Acerta melhor modelos densos (qwen3:8b: erro de
~13%), erra modelos híbridos/MoE com folga, e NÃO prevê pico de memória do sistema. A rodada de verdade manda.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Tudo que os scripts de teste produzem fica em logs/, a pasta que você compacta e me manda.
DEFAULT_OUTPUT = ROOT / "logs" / "estimativa-desempenho.txt"

# Sua máquina (RTX 3070 8 GB, Ryzen 5 5600G, 16 GB). A banda da RAM é a teórica de DDR4 dual channel
# (~51 GB/s a 3200 MT/s) descontada; ajuste com --cpu-bw se souber o valor real.
DEFAULT_HARDWARE = {
    "vram_gb": 8.0, "ram_gb": 16.0, "gpu_bw": 448.0, "cpu_bw": 40.0,
    "gpu_eff": 0.70, "cpu_eff": 0.60, "os_reserved_gb": 5.0, "gpu_overhead_gb": 0.5,
}

# kv: GB de cache por mil tokens de contexto (calibrado no qwen3:8b: ~0,125; os demais são palpites por família).
# active_gb: GB lidos por token (denso = os pesos todos; MoE = só os especialistas ativos).
# measured: o que você mediu na sua máquina (comparação de 08/10/2026), para validar o modelo de cálculo.
MODELS = [
    {"name": "qwen3:8b", "kind": "denso", "weights": 5.2, "active": 5.2, "kv": 0.125, "measured": {"tok_s": 68.9, "cpu_pct": 0}},
    {"name": "qwen3.5:4b", "kind": "denso*", "weights": 2.9, "active": 2.9, "kv": 0.06, "measured": {"tok_s": 98.9, "cpu_pct": 0}},
    {"name": "qwen3.5:9b", "kind": "híbrido*", "weights": 5.6, "active": 5.6, "kv": 0.08, "measured": {"tok_s": 50.9, "cpu_pct": 12}},
    {"name": "gemma4:12b", "kind": "denso", "weights": 7.9, "active": 7.9, "kv": 0.10, "measured": None},
    {"name": "gpt-oss:20b", "kind": "MoE", "weights": 14.0, "active": 2.4, "kv": 0.06, "measured": None},
    {"name": "qwen3-coder:30b", "kind": "MoE", "weights": 19.0, "active": 2.1, "kv": 0.10, "measured": None},
    {"name": "gemma4:26b", "kind": "MoE", "weights": 17.5, "active": 2.6, "kv": 0.10, "measured": None},
    {"name": "devstral:24b", "kind": "denso", "weights": 14.0, "active": 14.0, "kv": 0.16, "measured": None},
]


def estimate(model: dict, hardware: dict, ctx: int = 8192, kv8: bool = False) -> dict:
    """Quanto cabe na GPU, quanto vai para a RAM, se aguenta a RAM e a velocidade esperada."""

    kv = model["kv"] * ctx / 1000 * (0.5 if kv8 else 1.0)
    weights = model["weights"]
    gpu_room = max(0.0, hardware["vram_gb"] - hardware["gpu_overhead_gb"] - kv)
    on_gpu = min(weights, gpu_room)
    on_cpu = weights - on_gpu
    ram_room = max(0.0, hardware["ram_gb"] - hardware["os_reserved_gb"])
    gpu_fraction = on_gpu / weights if weights else 1.0

    gpu_speed = hardware["gpu_bw"] * hardware["gpu_eff"]
    cpu_speed = hardware["cpu_bw"] * hardware["cpu_eff"]
    seconds_per_token = model["active"] * gpu_fraction / gpu_speed + model["active"] * (1 - gpu_fraction) / cpu_speed

    if on_cpu <= 0.05:
        fit = "100% GPU"
    elif on_cpu <= ram_room:
        fit = f"parcial ({round(100 * on_cpu / weights)}% na CPU)"
    else:
        fit = "NÃO CABE (paginação em disco)"

    return {
        "name": model["name"], "kind": model["kind"], "kv_gb": round(kv, 2), "weights_gb": weights,
        "on_gpu_gb": round(on_gpu, 1), "on_cpu_gb": round(on_cpu, 1), "cpu_pct": round(100 * on_cpu / weights) if weights else 0,
        "fit": fit, "fits_ram": on_cpu <= ram_room,
        "ram_use_gb": round(on_cpu + hardware["os_reserved_gb"], 1),
        "tok_s": round(1 / seconds_per_token, 1) if fits_or_paged(on_cpu, ram_room) else round(1 / seconds_per_token / 10, 1),
        "freeze_risk": on_cpu > ram_room, "measured": model.get("measured"),
    }


def fits_or_paged(on_cpu: float, ram_room: float) -> bool:
    """Se não cabe na RAM, o disco entra no caminho e a velocidade despenca (ordem de 10x pior)."""

    return on_cpu <= ram_room


def verdict(row: dict) -> str:
    if row["freeze_risk"]:
        return "RISCO DE TRAVAR: precisa de mais memória do que o PC tem; tende a paginar em disco"

    if row["tok_s"] < 3:
        return "inviável como SMART (lento demais)"

    if row["tok_s"] < 8:
        return "lento, mas usável só como SMART raro"

    if row["tok_s"] < 20:
        return "usável como SMART"

    return "rápido; serve até como FAST"


def table(rows: list[dict]) -> str:
    headers = ["Modelo", "Tipo", "Pesos GB", "KV GB", "Encaixe", "Previsto tok/s", "Medido tok/s", "Leitura"]
    body = []

    for r in rows:
        measured = r["measured"]
        body.append([r["name"], r["kind"], str(r["weights_gb"]), str(r["kv_gb"]), r["fit"], str(r["tok_s"]),
                     str(measured["tok_s"]) if measured else "-", verdict(r) if not measured else "(validação)"])

    widths = [max(len(row[i]) for row in [headers] + body) for i in range(len(headers))]
    line = lambda cells: " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    return "\n".join([line(headers), "-+-".join("-" * w for w in widths)] + [line(row) for row in body])


def validation(rows: list[dict]) -> list[str]:
    """Compara a previsão com o que você mediu, para saber o quanto confiar nos números dos outros."""

    notes = []

    for r in rows:
        m = r["measured"]

        if not m:
            continue

        error = round(100 * (r["tok_s"] - m["tok_s"]) / m["tok_s"])
        fit_ok = (m["cpu_pct"] == 0) == (r["cpu_pct"] <= 2)
        notes.append(f"- {r['name']}: previu {r['tok_s']} tok/s, mediu {m['tok_s']} ({error:+d}%); encaixe previsto {r['fit']}, medido "
                     + ("100% GPU" if m["cpu_pct"] == 0 else f"{m['cpu_pct']}% na CPU") + ("" if fit_ok else "  <-- ERROU o encaixe"))

    return notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Estimativa de memória e velocidade dos modelos na sua máquina")
    parser.add_argument("--ctx", type=int, default=8192, help="janela de contexto (padrão 8192)")
    parser.add_argument("--kv8", action="store_true", help="cache de KV quantizado em 8 bits (metade da memória)")
    parser.add_argument("--vram", type=float, default=DEFAULT_HARDWARE["vram_gb"])
    parser.add_argument("--ram", type=float, default=DEFAULT_HARDWARE["ram_gb"])
    parser.add_argument("--cpu-bw", type=float, default=DEFAULT_HARDWARE["cpu_bw"], help="banda da RAM em GB/s")
    parser.add_argument("--gpu-bw", type=float, default=DEFAULT_HARDWARE["gpu_bw"], help="banda da VRAM em GB/s")
    parser.add_argument("--saida", default=str(DEFAULT_OUTPUT), help="arquivo onde a estimativa é gravada (padrão: logs/estimativa-desempenho.txt)")
    args = parser.parse_args(argv)

    from core.console import ensure_utf8_console

    ensure_utf8_console()

    hardware = {**DEFAULT_HARDWARE, "vram_gb": args.vram, "ram_gb": args.ram, "cpu_bw": args.cpu_bw, "gpu_bw": args.gpu_bw}
    rows = [estimate(m, hardware, args.ctx, args.kv8) for m in MODELS]
    lines = []
    say = lines.append

    say(f"Máquina: {args.vram:g} GB de VRAM, {args.ram:g} GB de RAM (~{hardware['os_reserved_gb']:g} GB reservados ao Windows), "
          f"banda GPU {args.gpu_bw:g} GB/s, RAM {args.cpu_bw:g} GB/s. Contexto {args.ctx}" + (", cache KV em 8 bits" if args.kv8 else "") + ".\n")
    say(table(rows))
    say("\nVALIDAÇÃO (previsto x medido por você):")
    say("\n".join(validation(rows)))
    say("\nAvisos: * = arquitetura que o modelo de cálculo representa mal. Os modelos MoE leem só os especialistas ativos, mas a divisão")
    say("por camadas do Ollama pode ler mais do que isso na prática. O que não cabe na RAM vira paginação em disco (velocidade /10 e risco de travar).")
    say("Confie nas CLASSES (cabe, parcial, não cabe) mais do que nos tok/s. A rodada de verdade manda.")

    text = "\n".join(lines)
    print(text)

    try:
        output = Path(args.saida)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        print(f"\n(salvo em {output})")
    except OSError as exc:
        print(f"\n(não consegui salvar a estimativa: {exc})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
