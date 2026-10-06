"""Saída de console à prova de página de código do Windows (cp1252/cp850)."""

import sys


def ensure_utf8_console() -> None:
    """
    Reconfigura stdout/stderr para UTF-8, trocando por '?' o que não puder ser mostrado.

    Sem isso, um print com "→", "✓" ou emoji derruba o programa num console Windows comum.
    """

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def safe_print(text: str = "") -> None:
    """print() que nunca levanta UnicodeEncodeError."""

    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def ask(prompt: str) -> str | None:
    """
    input() que não derruba o programa quando não há terminal (EOF) ou o usuário
    aperta Ctrl+C: nesses casos devolve None, que quem chama trata como "cancelar".
    """

    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt, OSError):
        print()
        return None
