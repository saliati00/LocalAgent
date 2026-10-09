"""
Revisa as decisões que o agente guardou na memória persistente. Decisões só entram no contexto depois de aprovadas.

    python scripts/revisar_memoria.py                 lista o que está pendente
    python scripts/revisar_memoria.py aprovar CHAVE   passa a valer no contexto do agente
    python scripts/revisar_memoria.py rejeitar CHAVE  apaga a decisão
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.console import ensure_utf8_console  # noqa: E402
from core.memory.store import MemoryStore  # noqa: E402


def main(argv=None, store: MemoryStore | None = None) -> int:
    ensure_utf8_console()

    argv = list(sys.argv[1:] if argv is None else argv)
    store = store or MemoryStore()

    if not argv:
        pending = store.pending_review()

        if not pending:
            print("Nenhuma decisão aguardando revisão.")
            return 0

        print("Decisões aguardando a sua revisão:\n")

        for item in pending:
            print(f"- {item['key']}: {item['value']}" + (f"  ({item['description']})" if item.get("description") else ""))

        print("\nUse: aprovar CHAVE   ou   rejeitar CHAVE")
        return 0

    if len(argv) != 2 or argv[0] not in ("aprovar", "rejeitar"):
        print("Uso: python scripts/revisar_memoria.py [aprovar|rejeitar CHAVE]")
        return 2

    if not store.review(argv[1], approve=argv[0] == "aprovar"):
        print(f"Não encontrei a decisão '{argv[1]}'.")
        return 1

    print(("Aprovada: passa a valer no contexto do agente." if argv[0] == "aprovar" else "Rejeitada e apagada."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
