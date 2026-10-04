import re
from pathlib import Path


CHECKLIST_PATTERN = re.compile(
    r"^\s*\*\s+\[([ xX])\]\s+(.+?)\s*$"
)

PHASE_PATTERN = re.compile(
    r"^\s*##\s+(FASE\s+\d+\s+[—-]\s+.+?)\s*$",
    re.IGNORECASE,
)


def extract_project_progress(path: str) -> dict:
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return {
            "success": False,
            "error": f"Arquivo não encontrado: {path}",
        }

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao ler projeto: {e}",
        }

    current_phase = None
    phases = []
    current_phase_data = None

    for line in content.splitlines():

        phase_match = PHASE_PATTERN.match(line)

        if phase_match:
            current_phase = phase_match.group(1).strip()

            current_phase_data = {
                "name": current_phase,
                "completed": [],
                "pending": [],
            }

            phases.append(current_phase_data)
            continue

        checklist_match = CHECKLIST_PATTERN.match(line)

        if checklist_match and current_phase_data is not None:

            checked = checklist_match.group(1).lower() == "x"
            item = checklist_match.group(2).strip()

            if checked:
                current_phase_data["completed"].append(item)
            else:
                current_phase_data["pending"].append(item)

    pending = []

    for phase in phases:

        for item in phase["pending"]:

            pending.append({
                "phase": phase["name"],
                "item": item,
            })

    next_action = pending[0] if pending else None

    return {
        "success": True,
        "current_phase": (
            next_action["phase"]
            if next_action
            else None
        ),
        "next_action": next_action["item"] if next_action else None,
        "pending_count": len(pending),
        "pending": pending,
        "phases": phases,
    }


def update_project_checklist(path: str, item_text: str, completed: bool = True) -> dict:
    """
    Atualiza com segurança o estado de um item de checklist no arquivo de especificação.
    Localiza a linha correspondente ao item e altera [ ] para [x] (ou vice-versa).
    """
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return {
            "success": False,
            "error": f"Arquivo não encontrado: {path}",
        }

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao ler arquivo: {e}",
        }

    lines = content.splitlines()
    target_clean = item_text.strip().lower()
    updated = False
    already_in_state = False
    new_mark = "x" if completed else " "

    for i, line in enumerate(lines):
        match = CHECKLIST_PATTERN.match(line)
        if match:
            current_item = match.group(2).strip()
            if current_item.lower() == target_clean:
                current_mark = match.group(1).lower()
                if (current_mark == "x" and completed) or (current_mark != "x" and not completed):
                    already_in_state = True
                # Substitui a marca mantendo a indentação e o texto
                prefix = line[:line.find("[") + 1]
                suffix = line[line.find("]"):]
                lines[i] = f"{prefix}{new_mark}{suffix}"
                updated = True
                break

    if not updated:
        # Tenta correspondência parcial caso haja pequenas variações de espaços
        for i, line in enumerate(lines):
            match = CHECKLIST_PATTERN.match(line)
            if match:
                current_item = match.group(2).strip()
                if target_clean in current_item.lower() or current_item.lower() in target_clean:
                    current_mark = match.group(1).lower()
                    if (current_mark == "x" and completed) or (current_mark != "x" and not completed):
                        already_in_state = True
                    prefix = line[:line.find("[") + 1]
                    suffix = line[line.find("]"):]
                    lines[i] = f"{prefix}{new_mark}{suffix}"
                    updated = True
                    break

    if not updated:
        return {
            "success": False,
            "error": f"Item não encontrado no checklist: '{item_text}'",
        }

    try:
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "success": True,
            "path": str(file_path),
            "item": item_text,
            "completed": completed,
            "already_in_state": already_in_state,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao salvar especificação: {e}",
        }


def format_project_summary(progress: dict) -> str:
    """
    Formata um resumo conciso e estruturado do progresso para inclusão no contexto do modelo.
    """
    if not progress.get("success"):
        return f"Erro ao obter estado do projeto: {progress.get('error', 'desconhecido')}"

    current_phase = progress.get("current_phase", "Não identificada")
    next_action = progress.get("next_action", "Nenhuma pendência")
    pending_count = progress.get("pending_count", 0)

    # Localiza dados da fase atual
    current_phase_data = None
    for p in progress.get("phases", []):
        if p.get("name") == current_phase:
            current_phase_data = p
            break

    summary_lines = [
        f"Fase atual: {current_phase}",
        f"Próxima ação pendente: {next_action}",
        f"Total de pendências restantes: {pending_count}",
    ]

    if current_phase_data:
        completed = current_phase_data.get("completed", [])
        pending = current_phase_data.get("pending", [])

        if completed:
            summary_lines.append(f"Itens já concluídos nesta fase ({len(completed)}):")
            for item in completed[-5:]:  # últimos 5 concluídos
                summary_lines.append(f"  ✓ {item}")

        if pending:
            summary_lines.append(f"Itens pendentes nesta fase ({len(pending)}):")
            for item in pending[:5]:  # próximos 5 pendentes
                summary_lines.append(f"  ○ {item}")

    return "\n".join(summary_lines)
