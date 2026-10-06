"""
Desfaz mudanças do agente: lista e restaura os backups automáticos (pasta backups/).

    python scripts/restaurar.py list [quantidade]
    python scripts/restaurar.py restore "<id do backup>"

Antes de qualquer arquivo ser sobrescrito pelo agente (write_file / replace_in_file),
o Harness guarda a versão anterior. Restaurar também guarda a versão atual, então
dá para voltar atrás do "voltar atrás".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backups import list_backups, restore_backup  # noqa: E402
from core.console import ensure_utf8_console  # noqa: E402


def cmd_list(limit: int) -> int:
    items = list_backups(limit)

    if not items:
        print("Nenhum backup ainda. Eles aparecem quando o agente sobrescreve um arquivo existente.")
        return 0

    print(f"Backups mais recentes (até {limit}):\n")

    for item in items:
        print(f"- {item['id']}  ({item['size']} bytes)")

    print('\nPara restaurar:  python scripts/restaurar.py restore "<id>"')

    return 0


def cmd_restore(backup_id: str) -> int:
    if not sys.stdin.isatty():
        print("Restaurar exige um terminal interativo. Nada foi alterado.")
        return 1

    answer = input(f"Restaurar '{backup_id}' sobre o arquivo atual? (S/N): ").strip().upper()

    if answer not in {"S", "SIM", "Y", "YES"}:
        print("Cancelado. Nada foi alterado.")
        return 1

    result = restore_backup(backup_id)

    if not result["success"]:
        print(result["error"])
        return 1

    print(f"Restaurado: {result['restored']}")

    return 0


def main(argv: list[str]) -> int:
    ensure_utf8_console()

    if len(argv) >= 2 and argv[1] == "list":
        limit = int(argv[2]) if len(argv) >= 3 and argv[2].isdigit() else 20
        return cmd_list(limit)

    if len(argv) >= 3 and argv[1] == "restore":
        return cmd_restore(argv[2])

    print(__doc__)

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
