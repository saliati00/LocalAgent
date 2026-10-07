"""
Backup automático de arquivos antes de serem sobrescritos pelas tools de escrita.

O agente não tem tool para restaurar: quem desfaz é o usuário, com
`python scripts/restaurar.py`. A pasta backups/ é protegida contra escrita do agente.
"""

import shutil
from datetime import datetime
from pathlib import Path

from core.paths import BACKUPS_DIR, PROJECT_ROOT

MAX_BACKUP_BYTES = 2_000_000
MAX_BACKUP_DIRS = 300


def _relative_id(target: Path) -> str:
    """Caminho relativo ao projeto (ou _fora/<nome> para arquivos de fora dele)."""

    try:
        return str(target.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return "_fora/" + target.name


def backup_file(target: Path) -> str | None:
    """
    Copia o arquivo existente para backups/<data-hora>/<caminho relativo>.
    Retorna o id do backup ('<data-hora>/<caminho>') ou None se não houve cópia.
    Nunca levanta exceção: falhar em fazer backup não pode impedir o trabalho.
    """

    try:
        target = Path(target)

        if not target.is_file() or target.stat().st_size > MAX_BACKUP_BYTES:
            return None

        base_stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        relative = _relative_id(target)

        # Dois backups do mesmo arquivo no mesmo milissegundo não podem se sobrescrever.
        stamp = base_stamp
        counter = 1

        while (BACKUPS_DIR / stamp / relative).exists():
            counter += 1
            stamp = f"{base_stamp}-{counter}"

        destination = BACKUPS_DIR / stamp / relative

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)

        prune()

        return f"{stamp}/{relative}"
    except OSError:
        return None


def prune(max_dirs: int = MAX_BACKUP_DIRS) -> None:
    """Mantém só as `max_dirs` pastas de backup mais recentes."""

    if not BACKUPS_DIR.exists():
        return

    folders = sorted(path for path in BACKUPS_DIR.iterdir() if path.is_dir())

    for old in folders[:-max_dirs] if len(folders) > max_dirs else []:
        shutil.rmtree(old, ignore_errors=True)


def list_backups(limit: int = 20) -> list[dict]:
    """Backups mais recentes primeiro: [{'id', 'file', 'stamp', 'size'}]."""

    if not BACKUPS_DIR.exists():
        return []

    found = []

    for folder in sorted((p for p in BACKUPS_DIR.iterdir() if p.is_dir()), reverse=True):
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue

            relative = str(path.relative_to(folder)).replace("\\", "/")

            found.append({
                "id": f"{folder.name}/{relative}",
                "file": relative,
                "stamp": folder.name,
                "size": path.stat().st_size,
            })

            if len(found) >= limit:
                return found

    return found


def restore_backup(backup_id: str) -> dict:
    """
    Devolve o conteúdo do backup ao lugar original. Antes de sobrescrever, guarda a
    versão atual como um novo backup (restaurar também é reversível).
    """

    stamp, _, relative = (backup_id or "").partition("/")

    if not stamp or not relative or ".." in relative.split("/"):
        return {"success": False, "error": "Id de backup inválido."}

    source = BACKUPS_DIR / stamp / relative

    if not source.is_file():
        return {"success": False, "error": f"Backup não encontrado: {backup_id}"}

    if relative.startswith("_fora/"):
        return {
            "success": False,
            "error": "Este backup veio de fora do projeto; copie-o manualmente de " + str(source),
        }

    destination = PROJECT_ROOT / relative

    backup_file(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    return {"success": True, "restored": str(destination)}
