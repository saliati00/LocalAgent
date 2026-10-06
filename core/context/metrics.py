"""Medição do tamanho das seções do prompt (diagnóstico de contexto)."""

import json

# Estimativa grosseira para texto em português com tokenizers de LLMs abertos.
CHARS_PER_TOKEN = 3.0


NEAR_LIMIT_RATIO = 0.95


def context_pressure(prompt_tokens: int, num_ctx: int) -> str:
    """
    Classifica o uso da janela pelo prompt_eval_count devolvido pelo modelo.

    'truncated': o prompt chegou ao limite (o Ollama descarta o início da conversa,
                 inclusive o objetivo, sem avisar).
    'near_limit': acima de 95% da janela.
    'ok': abaixo disso.
    """

    if num_ctx <= 0:
        return "ok"

    if prompt_tokens >= num_ctx - 8:
        return "truncated"

    if prompt_tokens >= num_ctx * NEAR_LIMIT_RATIO:
        return "near_limit"

    return "ok"


def estimate_tokens(text: str) -> int:
    return int(len(text or "") / CHARS_PER_TOKEN)


def describe_prompt_sections(sections: dict[str, str], context_window: int | None = None) -> str:
    """
    Retorna um JSON com caracteres e tokens estimados por seção, e o total.

    Quando context_window é informado, inclui a fração ocupada.
    """

    report = {
        name: {"chars": len(text or ""), "est_tokens": estimate_tokens(text)}
        for name, text in sections.items()
    }

    # Seções "detail:..." detalham outra seção (ex.: skills dentro do system prompt)
    # e não podem ser somadas de novo no total.
    counted = {name: item for name, item in report.items() if not name.startswith("detail:")}

    total_chars = sum(item["chars"] for item in counted.values())
    total_tokens = sum(item["est_tokens"] for item in counted.values())

    report["_total"] = {"chars": total_chars, "est_tokens": total_tokens}

    if context_window:
        report["_total"]["fraction_of_window"] = round(total_tokens / context_window, 2)

    return json.dumps(report, ensure_ascii=False)
