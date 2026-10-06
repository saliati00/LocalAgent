"""
Pacote de passagem entre modelos (FAST <-> SMART).

O KV cache não é compartilhável entre modelos diferentes, então o novo modelo
precisa reprocessar tudo o que receber. Em vez de herdar o histórico inteiro
(com os loops e erros do modelo anterior), ele recebe um resumo curto e
determinístico montado pelo Harness.
"""

from typing import Any

MAX_PACKET_CHARS = 3500
MAX_RESULT_CHARS = 300


def _get(message: Any, key: str, default: Any = "") -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _shorten(text: Any, limit: int) -> str:
    text = " ".join(str(text).split())

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def _looks_like_error(content: str) -> bool:
    lowered = content.lower()

    return "'success': false" in lowered or "'error'" in lowered or "blocked_by_harness" in lowered


def build_handover_packet(
    goal: str,
    from_model: str | None,
    to_model: str | None,
    reason: str,
    messages: list,
    actions_completed: list[str] | None = None,
    phase: str | None = None,
    next_action: str | None = None,
    max_chars: int = MAX_PACKET_CHARS,
) -> str:
    tool_messages = [m for m in messages if _get(m, "role") == "tool"]

    last_results = [
        f"- {_get(m, 'tool_name', 'ferramenta')}: {_shorten(_get(m, 'content'), MAX_RESULT_CHARS)}"
        for m in tool_messages[-4:]
    ]

    recent_errors = [
        f"- {_get(m, 'tool_name', 'ferramenta')}: {_shorten(_get(m, 'content'), MAX_RESULT_CHARS)}"
        for m in tool_messages
        if _looks_like_error(str(_get(m, "content")))
    ][-3:]

    done = [_shorten(action, 120) for action in (actions_completed or [])[-8:]]

    lines = [
        "[HARNESS] PASSAGEM DE TAREFA ENTRE MODELOS",
        f"De: {from_model or 'desconhecido'}  ->  Para: {to_model or 'desconhecido'}",
        f"Motivo: {_shorten(reason, 300)}",
        "",
        f"OBJETIVO: {_shorten(goal, 500)}",
    ]

    if phase:
        lines.append(f"FASE: {phase}")

    if next_action:
        lines.append(f"PENDÊNCIA ATUAL: {next_action}")

    lines.append("")
    lines.append("AÇÕES JÁ CONCLUÍDAS (não repita):")
    lines.extend(f"- {item}" for item in done or ["nenhuma"])

    lines.append("")
    lines.append("ÚLTIMOS RESULTADOS DE FERRAMENTAS:")
    lines.extend(last_results or ["- nenhum"])

    if recent_errors:
        lines.append("")
        lines.append("ERROS RECENTES:")
        lines.extend(recent_errors)

    lines.extend([
        "",
        "INSTRUÇÕES: assuma a etapa a partir daqui. Não repita consultas já feitas.",
        "Se não for possível progredir, explique o bloqueio em uma resposta curta.",
    ])

    packet = "\n".join(lines)

    if len(packet) > max_chars:
        packet = packet[: max_chars - 40].rstrip() + "\n[... pacote truncado pelo Harness ...]"

    return packet
