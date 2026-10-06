from tools.filesystem import (
    list_directory,
    read_file,
    write_file,
    replace_in_file,
)

from tools.terminal import run_command
from tools.environment import check_tools
from tools.search import search_files
from core.skills.loader import load_skill
from core.skills.proposal import propose_skill

from tools.web import (
    web_search,
    fetch_url,
    download_file,
)

from core.harness.project_progress import (
    extract_project_progress,
    update_project_checklist,
)
from core.harness.acceptance import check_checklist_acceptance

from core.memory.store import MemoryStore
from core.paths import PROJECT_SPEC_PATH
from tools.models import (
    get_model_registry,
    register_model_candidate,
    set_smart_candidate_for_benchmark,
    set_active_smart_model,
)

PROJECT_SPEC = str(PROJECT_SPEC_PATH)
_memory_store = MemoryStore()


def save_memory(category: str, key: str, value: str, description: str = "") -> dict:
    """
    Salva uma informação na memória persistente do agente.
    Categorias válidas: 'environment', 'decisions', 'progress', 'notes'.
    """
    return _memory_store.set(category, key, value, description)


def get_memory(category: str, key: str = "") -> dict:
    """
    Consulta a memória persistente do agente.
    Se 'key' for informada, retorna a entrada correspondente.
    Se 'key' for omitida ou vazia, retorna todas as entradas da categoria.
    """
    if key and key.strip():
        val = _memory_store.get(category, key.strip())
        entry = _memory_store.get_entry(category, key.strip())
        return {
            "success": True,
            "found": entry is not None,
            "category": category,
            "key": key.strip(),
            "value": val,
            "entry": entry,
        }
    return {
        "success": True,
        "category": category,
        "entries": _memory_store.get_category(category),
    }


def update_spec_checklist_tool(item: str, completed: bool = True) -> dict:
    """
    Atualiza o estado de um item no checklist da especificação principal (specs/projeto.md).
    Marca [x] para concluído ou [ ] para pendente.
    Exige o cumprimento rigoroso dos critérios de aceitação do Harness antes de marcar concluído.
    """
    if completed:
        accepted, rejection_reason = check_checklist_acceptance(item, completed=True, project_spec_path=PROJECT_SPEC)
        if not accepted:
            return {
                "success": False,
                "error": rejection_reason,
                "acceptance_criteria_failed": True,
                "tool_error": True,
            }

    res = update_project_checklist(PROJECT_SPEC, item, completed=completed)
    if res["success"]:
        prog = extract_project_progress(PROJECT_SPEC)
        res["next_action"] = prog.get("next_action")
        res["current_phase"] = prog.get("current_phase")
        res["pending_count"] = prog.get("pending_count")
        if res.get("already_in_state"):
            res["notice"] = (
                f"O item '{item}' já estava com status completed={completed} no checklist. "
                f"A próxima pendência ativa do projeto é: '{res['next_action']}'."
            )
    return res


def get_project_status() -> dict:
    """
    Retorna o estado atual estruturado do projeto focado na fase atual e próxima ação.
    """
    prog = extract_project_progress(PROJECT_SPEC)
    if not prog.get("success"):
        return prog

    current_phase = prog.get("current_phase")
    next_action = prog.get("next_action")

    phase_data = None
    for p in prog.get("phases", []):
        if p.get("name") == current_phase:
            phase_data = p
            break

    return {
        "success": True,
        "current_phase": current_phase,
        "next_action": next_action,
        "pending_in_current_phase": phase_data.get("pending", []) if phase_data else [],
        "completed_in_current_phase": phase_data.get("completed", []) if phase_data else [],
        "total_pending_all_phases": prog.get("pending_count", 0),
        "directive": (
            f"Foque exclusivamente na pendência imediata: '{next_action}'. "
            "Execute as ferramentas necessárias, valide o resultado e use "
            f"'update_spec_checklist' para marcar '{next_action}' como concluído."
        ),
    }


TOOLS = {
    "list_directory": list_directory,
    "read_file": read_file,
    "write_file": write_file,
    "replace_in_file": replace_in_file,
    "run_command": run_command,
    "web_search": web_search,
    "fetch_url": fetch_url,
    "download_file": download_file,
    "check_tools": check_tools,
    "search_files": search_files,
    "load_skill": load_skill,
    "propose_skill": propose_skill,
    "update_spec_checklist": update_spec_checklist_tool,
    "get_project_status": get_project_status,
    "save_memory": save_memory,
    "get_memory": get_memory,
    "get_model_registry": get_model_registry,
    "register_model_candidate": register_model_candidate,
    "set_smart_candidate_for_benchmark": set_smart_candidate_for_benchmark,
    "set_active_smart_model": set_active_smart_model,
}


# =========================================================
# VALIDAÇÃO DE ARGUMENTOS
# =========================================================

ALLOWED_ARGUMENTS = {
    "list_directory": {
        "path",
    },

    "read_file": {
        "path",
        "start_line",
        "end_line",
    },

    "write_file": {
        "path",
        "content",
    },

    "replace_in_file": {
        "path",
        "target",
        "replacement",
    },

    "run_command": {
        "command",
        "reason",
    },

    "web_search": {
        "query",
        "max_results",
    },

    "fetch_url": {
        "url",
        "max_length",
    },

    "download_file": {
        "url",
        "destination",
    },

    "check_tools": {
        "names",
    },

    "search_files": {
        "pattern",
        "path",
        "glob",
        "max_results",
    },

    "load_skill": {
        "name",
    },

    "propose_skill": {
        "name",
        "description",
        "triggers",
        "when_to_use",
        "steps",
        "validation",
        "limits",
        "tools",
        "used_web",
        "source_task",
    },

    "update_spec_checklist": {
        "item",
        "completed",
    },

    "get_project_status": set(),

    "save_memory": {
        "category",
        "key",
        "value",
        "description",
    },

    "get_memory": {
        "category",
        "key",
    },

    "get_model_registry": {
        "role",
    },

    "register_model_candidate": {
        "name",
        "role",
        "backend",
        "size_gb",
        "vram_gb",
        "description",
        "justification",
        "context_window",
    },

    "set_active_smart_model": {
        "model_name",
        "justification",
    },

    "set_smart_candidate_for_benchmark": {
        "model_name",
        "rationale",
    },
}


REQUIRED_ARGUMENTS = {
    "list_directory": {
        "path",
    },

    "read_file": {
        "path",
    },

    "write_file": {
        "path",
        "content",
    },

    "replace_in_file": {
        "path",
        "target",
        "replacement",
    },

    "run_command": {
        "command",
        "reason",
    },

    "web_search": {
        "query",
    },

    "fetch_url": {
        "url",
    },

    "download_file": {
        "url",
        "destination",
    },

    "check_tools": {
        "names",
    },

    "search_files": set(),

    "load_skill": {
        "name",
    },

    "propose_skill": {
        "name",
        "description",
        "triggers",
        "when_to_use",
        "steps",
        "validation",
        "limits",
    },

    "update_spec_checklist": {
        "item",
    },

    "get_project_status": set(),

    "save_memory": {
        "category",
        "key",
        "value",
    },

    "get_memory": {
        "category",
    },

    "get_model_registry": set(),

    "register_model_candidate": {
        "name",
        "role",
        "backend",
        "size_gb",
        "vram_gb",
        "description",
        "justification",
    },

    "set_active_smart_model": {
        "model_name",
    },

    "set_smart_candidate_for_benchmark": {
        "model_name",
    },
}


def validate_arguments(
    name: str,
    arguments: dict,
) -> tuple[bool, str]:

    if not isinstance(arguments, dict):
        return (
            False,
            "Argumentos da ferramenta devem ser um objeto/dicionário.",
        )

    if name not in ALLOWED_ARGUMENTS:
        return (
            False,
            f"Ferramenta desconhecida: {name}",
        )

    allowed = ALLOWED_ARGUMENTS[name]
    required = REQUIRED_ARGUMENTS[name]
    provided = set(arguments.keys())

    missing = required - provided
    if missing:
        return (
            False,
            "Argumentos obrigatórios ausentes: "
            + ", ".join(sorted(missing)),
        )

    unknown = provided - allowed
    if unknown:
        return (
            False,
            "Argumentos não suportados pela ferramenta: "
            + ", ".join(sorted(unknown)),
        )

    return True, ""


def execute_tool(
    name: str,
    arguments: dict,
) -> dict:

    tool = TOOLS.get(name)

    if tool is None:
        return {
            "success": False,
            "error": f"Ferramenta desconhecida: {name}",
            "tool_error": True,
        }

    valid, error = validate_arguments(
        name,
        arguments,
    )

    if not valid:
        return {
            "success": False,
            "error": error,
            "tool_error": True,
        }

    try:
        result = tool(**arguments)

        if not isinstance(result, dict):
            return {
                "success": False,
                "error": "A ferramenta retornou um resultado inválido.",
                "tool_error": True,
            }

        return result

    except TypeError as e:
        return {
            "success": False,
            "error": f"Argumentos inválidos: {e}",
            "tool_error": True,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "tool_error": True,
        }


def list_tools() -> list:
    return list(TOOLS.keys())
