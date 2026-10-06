"""Leitura e escrita do cabeçalho (frontmatter) simples das Skills."""

LIST_FIELDS = {"triggers", "tools"}
BOOL_FIELDS = {"used_web"}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Separa o cabeçalho '---' ... '---' do corpo.

    Retorna ({}, texto) quando não há cabeçalho (Skills antigas).
    Listas são separadas por vírgula; used_web vira booleano.
    """

    text = text or ""
    stripped = text.lstrip("﻿")

    if not stripped.startswith("---"):
        return {}, text

    lines = stripped.splitlines()

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break

    if end is None:
        return {}, text

    meta: dict = {}

    for line in lines[1:end]:
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key in LIST_FIELDS:
            meta[key] = [item.strip() for item in value.split(",") if item.strip()]
        elif key in BOOL_FIELDS:
            meta[key] = value.lower() in {"true", "sim", "yes", "1"}
        else:
            meta[key] = value

    body = "\n".join(lines[end + 1:]).lstrip("\n")

    return meta, body


def render_frontmatter(meta: dict) -> str:
    lines = ["---"]

    for key, value in meta.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)

        lines.append(f"{key}: {rendered}")

    lines.append("---")

    return "\n".join(lines) + "\n"
