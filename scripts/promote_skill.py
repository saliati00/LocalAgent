"""
Revisão e promoção de Skills propostas pelo agente (uso humano).

    python scripts/promote_skill.py list
    python scripts/promote_skill.py show <nome>
    python scripts/promote_skill.py promote <nome>
    python scripts/promote_skill.py reject <nome>

O agente só grava rascunhos em skills_pending/. Para uma Skill passar a valer,
você lê o texto, e confirma digitando o nome dela.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.console import ask, ensure_utf8_console  # noqa: E402
from core.skills.proposal import (  # noqa: E402
    list_pending,
    promote_skill,
    read_pending,
    reject_skill,
)


def cmd_list() -> int:
    items = list_pending()

    if not items:
        print("Nenhum rascunho aguardando revisão.")
        return 0

    print("Rascunhos aguardando revisão:\n")

    for item in items:
        web = "  [USOU A WEB - leia com atenção]" if item["used_web"] else ""
        print(f"- {item['name']}: {item['description']}{web}")

    print("\nPara ler um deles:  python scripts/promote_skill.py show <nome>")

    return 0


def cmd_show(name: str) -> int:
    info = read_pending(name)

    if not info["success"]:
        print(info["error"])
        return 1

    print(info["text"])
    print("-" * 60)

    if info["valid"]:
        print("Validação automática: OK")
    else:
        print("Validação automática: FALHOU")
        for error in info["errors"]:
            print(f"  - {error}")

    return 0


def cmd_promote(name: str) -> int:
    info = read_pending(name)

    if not info["success"]:
        print(info["error"])
        return 1

    print(info["text"])
    print("-" * 60)

    if not info["valid"]:
        print("Esta Skill NÃO passa na validação e não pode ser promovida:")
        for error in info["errors"]:
            print(f"  - {error}")
        return 1

    if info["used_web"]:
        print("ATENÇÃO: o agente usou a internet nesta tarefa. Texto vindo de páginas")
        print("pode conter instruções escondidas. Leia a Skill inteira antes de aprovar.")

    if not sys.stdin.isatty():
        print("Promoção exige um terminal interativo. Nada foi alterado.")
        return 1

    answer = (ask(f"Digite o nome da Skill ('{name}') para PROMOVER, ou ENTER para cancelar: ") or "").strip()

    if answer != name:
        print("Cancelado. Nada foi alterado.")
        return 1

    if info["used_web"]:
        if (ask("Digite REVISEI para confirmar que leu a Skill inteira: ") or "").strip() != "REVISEI":
            print("Cancelado. Nada foi alterado.")
            return 1

    result = promote_skill(name)

    if not result["success"]:
        print(result["error"])
        return 1

    print(f"Skill '{name}' promovida: {result['path']}")
    print("Dica: registre no git com  git add skills && git commit -m \"skill: " + name + "\"")

    return 0


def cmd_reject(name: str) -> int:
    result = reject_skill(name)

    if not result["success"]:
        print(result["error"])
        return 1

    print(f"Rascunho '{name}' movido para {result['path']}")

    return 0


def main(argv: list[str]) -> int:
    ensure_utf8_console()

    if len(argv) >= 2 and argv[1] == "list":
        return cmd_list()

    if len(argv) >= 3 and argv[1] == "show":
        return cmd_show(argv[2])

    if len(argv) >= 3 and argv[1] == "promote":
        return cmd_promote(argv[2])

    if len(argv) >= 3 and argv[1] == "reject":
        return cmd_reject(argv[2])

    print(__doc__)

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
