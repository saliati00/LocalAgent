import datetime
import json
import os
import re
import time
from pathlib import Path
from core.paths import PROJECT_ROOT, PROJECT_SPEC_PATH, TASKS_DIR
from core.prompts import list_prompts, load_prompt
from core.tasks import (
    TASK_MARKER,
    acceptance_command,
    build_task_prompt,
    find_task_number,
    list_tasks,
    run_acceptance,
    task_number_from_prompt,
)
import ollama

from core.context.manager import ContextManager
from core.harness.completion import (
    check_completion,
    build_continuation_reason,
)
from core.console import ensure_utf8_console
from core.context.metrics import (
    context_pressure,
    describe_prompt_sections,
    estimate_tokens,
    tokens_per_second,
)
from core.harness.handover import build_handover_packet
from core.harness.logger import log, new_run_id
from core.harness.memo import ToolMemo
from core.harness.repetition import RepeatedResponseDetector
from core.harness.permissions import parse_command
from core.harness.project_progress import (
    extract_project_progress,
    format_project_summary,
    update_project_checklist,
)
from core.harness.stagnation import StagnationDetector
from core.harness.task_constraints import TaskConstraints
from core.harness.task_state import TaskState
from core.memory.store import MemoryStore
from core.router.model_router import ModelRouter
from core.skills.loader import (
    SKILLS_BUDGET_CHARS,
    list_skills,
    format_skills_context,
    load_skill,
    match_skills,
)
from tools.manager import execute_tool
from tools.terminal import check_constraints


# Servidor e janela de contexto podem ser trocados só numa execução (comparação de configurações).
OLLAMA_URL = os.environ.get("LOCALAGENT_OLLAMA_URL", "").strip() or "http://localhost:11434"



def _float_from_environment(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default

    return value if 10 <= value <= 7200 else default


# Modelos grandes com parte na CPU geram devagar; a comparação de SMARTs aumenta o tempo por chamada.
client = ollama.Client(
    host=OLLAMA_URL,
    timeout=_float_from_environment("LOCALAGENT_CALL_TIMEOUT", 120),
)


def _context_from_environment(default: int = 8192) -> int:
    try:
        value = int(os.environ.get("LOCALAGENT_NUM_CTX", "").strip() or default)
    except ValueError:
        return default

    return value if 2048 <= value <= 131072 else default


NUM_CTX = _context_from_environment()

# Raciocínio do modelo (think) desligado por padrão: é mais rápido e cabe na janela. A comparação liga para medir.
THINK = os.environ.get("LOCALAGENT_THINK", "").strip().lower() in {"1", "true", "sim"}
MAX_ITERATIONS = 30
MAX_ESCALATIONS = 3

# Tarefas numeradas com teste de aceite: quantas vezes o Harness roda o teste antes de pedir ajuda.
MAX_ACCEPTANCE_ATTEMPTS = 3

# Descrições do schema de tools enviadas ao modelo (o schema completo continua em TOOLS).
COMPACT_TOOL_SCHEMA = True
TOOL_DESCRIPTION_MAX_CHARS = 110
PARAM_DESCRIPTION_MAX_CHARS = 80
# Parâmetros com valores restritos (role, category) ou regras (name do propose_skill)
# mantêm a descrição curta.
SELF_EXPLANATORY_PARAMS = {
    "path", "content", "query", "url", "names", "key", "value",
    "command", "item", "destination", "model_name", "reason",
    "target", "replacement",
}

# Memória persistente no prompt: no máximo isto (entradas mais recentes primeiro).
MEMORY_PROMPT_MAX_CHARS = 1500

# Acima desta fração da janela, o prompt fixo (sistema + tools + pedido) é perigoso.
PROMPT_BUDGET_WARN_RATIO = 0.7
SMART_MAX_ITERATIONS = 8

# Só o modelo SMART pode propor Skills novas (rascunhos que um humano promove).
ONLY_SMART_CAN_PROPOSE_SKILLS = True

WEB_TOOLS = {"web_search", "fetch_url", "download_file"}
PROJECT_SPEC = str(PROJECT_SPEC_PATH)


# =========================================================
# FERRAMENTAS DISPONÍVEIS PARA O MODELO
# =========================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista arquivos e diretórios existentes em um caminho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho do diretório."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê o conteúdo de um arquivo. Permite ler seções com start_line e end_line.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho do arquivo."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Linha inicial opcional (1-indexada)."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Linha final opcional (inclusive)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Cria um novo arquivo (e as pastas que faltarem) ou substitui um arquivo inteiro dentro do projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho do arquivo."
                    },
                    "content": {
                        "type": "string",
                        "description": "Conteúdo que será escrito."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Substitui um trecho exato de texto dentro de um arquivo existente. O trecho alvo deve ser único.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho do arquivo."
                    },
                    "target": {
                        "type": "string",
                        "description": "Trecho exato que será substituído (inclua linhas de contexto para unicidade)."
                    },
                    "replacement": {
                        "type": "string",
                        "description": "Novo trecho que substituirá o original."
                    }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Executa um comando no terminal dentro do projeto com .venv ativo. A justificativa é obrigatória.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Comando exato que será executado (ex.: pytest -v, command -v git)."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Explique o que será feito e por que."
                    }
                },
                "required": ["command", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa na internet e retorna URLs e snippets relevantes para consultar documentação ou repositórios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termos da pesquisa."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Número máximo de resultados (padrão 5)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Acessa uma página web, documentação ou endpoint de API (como GitHub) e retorna o texto limpo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL da página ou documentação para leitura."
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Máximo de caracteres retornados (opcional)."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "Baixa um arquivo da internet para um destino dentro do projeto ou do diretório temporário. Caminhos protegidos do Harness são recusados e há limite de tamanho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL do arquivo."
                    },
                    "destination": {
                        "type": "string",
                        "description": "Caminho de destino do arquivo."
                    }
                },
                "required": ["url", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Procura um texto nas linhas dos arquivos do projeto, ou lista arquivos pelo nome (sem pattern). Resultados curtos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Texto a procurar (ignora maiúsculas). Vazio = só lista os arquivos que casam com glob."
                    },
                    "path": {
                        "type": "string",
                        "description": "Pasta dentro do projeto (padrão: raiz)."
                    },
                    "glob": {
                        "type": "string",
                        "description": "Filtro de nome de arquivo, ex.: *.py (padrão: todos)."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Máximo de resultados (padrão 30, limite 50)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_tools",
            "description": "Verifica de uma só vez quais ferramentas/executáveis existem no PATH (somente leitura). Use no lugar de várias chamadas 'command -v' ou 'where'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Nomes dos executáveis (ex.: [\"git\", \"python\", \"cmake\"]). Máximo 30."
                    }
                },
                "required": ["names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Lê o texto completo de uma Skill (procedimento operacional) pelo nome. Use para as Skills listadas como disponíveis sob demanda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome da Skill (ex.: environment)."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_skill",
            "description": "Propõe uma NOVA Skill como rascunho (não entra em uso até o usuário revisar e promover). Só para procedimentos que já funcionaram em tarefas reais. Somente o modelo SMART pode usar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome em minúsculas com hífen (ex.: checar-release-github)."
                    },
                    "description": {
                        "type": "string",
                        "description": "Uma linha (até 160 caracteres) dizendo para que serve."
                    },
                    "triggers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Palavras que ativam a Skill (3+ caracteres cada, máximo 12)."
                    },
                    "when_to_use": {
                        "type": "string",
                        "description": "Quando aplicar este procedimento."
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Passos do procedimento, em ordem."
                    },
                    "validation": {
                        "type": "string",
                        "description": "Como confirmar que deu certo (idealmente um comando verificável)."
                    },
                    "limits": {
                        "type": "string",
                        "description": "O que a Skill NÃO deve fazer."
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools usadas pelo procedimento (opcional)."
                    },
                    "used_web": {
                        "type": "boolean",
                        "description": "Preenchido pelo Harness; qualquer valor informado é ignorado."
                    },
                    "source_task": {
                        "type": "string",
                        "description": "Resumo da tarefa real que originou o procedimento (opcional)."
                    }
                },
                "required": ["name", "description", "triggers", "when_to_use", "steps", "validation", "limits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_spec_checklist",
            "description": "Atualiza o checklist de specs/projeto.md marcando uma pendência como concluída [x] ou pendente [ ].",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "Texto exato do item da pendência no checklist."
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "True para marcar concluído [x], False para pendente [ ]. Padrão True."
                    }
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_status",
            "description": "Consulta o estado atual estruturado do projeto focado na fase e pendência atuais.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Salva uma informação na memória persistente do agente. Categorias: 'environment', 'decisions', 'progress', 'notes'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Categoria da memória (environment, decisions, progress, notes)."
                    },
                    "key": {
                        "type": "string",
                        "description": "Identificador único da informação."
                    },
                    "value": {
                        "type": "string",
                        "description": "Valor ou dado a ser memorizado."
                    },
                    "description": {
                        "type": "string",
                        "description": "Contexto ou explicação opcional."
                    }
                },
                "required": ["category", "key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory",
            "description": "Consulta a memória persistente do agente. Se 'key' for omitida, retorna toda a categoria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Categoria da memória (environment, decisions, progress, notes)."
                    },
                    "key": {
                        "type": "string",
                        "description": "Chave opcional a consultar."
                    }
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_registry",
            "description": "Consulta os modelos cadastrados no Model Registry (models/registry.json), incluindo o modelo FAST ativo, SMART ativo e candidatos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Filtro opcional pelo papel do modelo ('fast', 'smart'). Se omitido, retorna todos."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "register_model_candidate",
            "description": "Registra formalmente um modelo candidato no Model Registry e na memória persistente com justificativa técnica obrigatória.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Identificador do modelo (ex.: 'qwen2.5-coder:14b')."
                    },
                    "role": {
                        "type": "string",
                        "description": "Papel do modelo no sistema ('fast', 'smart', 'heavy')."
                    },
                    "backend": {
                        "type": "string",
                        "description": "Backend de execução ('ollama' ou 'llama.cpp')."
                    },
                    "size_gb": {
                        "type": "number",
                        "description": "Tamanho estimado do arquivo em GB (ex.: 9.0)."
                    },
                    "vram_gb": {
                        "type": "number",
                        "description": "VRAM estimada para pesos e contexto em GB (ex.: 8.0)."
                    },
                    "description": {
                        "type": "string",
                        "description": "Descrição das capacidades e perfil do modelo."
                    },
                    "justification": {
                        "type": "string",
                        "description": "Justificativa técnica detalhada de compatibilidade com o hardware (RTX 3070 8GB VRAM) e critérios de escolha."
                    },
                    "context_window": {
                        "type": "integer",
                        "description": "Janela de contexto padrão em tokens (padrão 32768)."
                    }
                },
                "required": ["name", "role", "backend", "size_gb", "vram_gb", "description", "justification"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_smart_candidate_for_benchmark",
            "description": "Marca um candidato já registrado como 'selected_for_benchmark'. Não adota o modelo e não autoriza download; a adoção exige benchmark e set_active_smart_model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "Nome do candidato já registrado no Model Registry."
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Justificativa da seleção para benchmark."
                    }
                },
                "required": ["model_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_active_smart_model",
            "description": "Define qual modelo é o modelo ativo da classe SMART (especialista) no Model Registry e na memória de decisões.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "Nome do modelo a ser definido como SMART ativo (ex.: 'qwen2.5-coder:14b')."
                    },
                    "justification": {
                        "type": "string",
                        "description": "Justificativa da ativação."
                    }
                },
                "required": ["model_name"]
            }
        }
    }
]


# =========================================================
# RESTRIÇÕES DA TAREFA
# =========================================================

def check_task_constraint(
    tool_name: str,
    arguments: dict,
    constraints: TaskConstraints,
) -> dict | None:
    """
    Aplica as restrições da tarefa a chamadas de run_command.

    Usa a mesma verificação do terminal (que entende wrappers como sudo/env),
    em vez de olhar só a primeira palavra do comando.
    """

    if tool_name != "run_command":
        return None

    parts, parse_error = parse_command(arguments.get("command", ""))

    if parse_error:
        # run_command devolve o erro de parsing ao modelo.
        return None

    return check_constraints(parts, constraints)


def _first_sentence(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    sentence = text.split(". ")[0]

    if len(sentence) > limit:
        sentence = sentence[: limit - 3].rstrip() + "..."

    return sentence


def compact_tools(tools: list) -> list:
    """
    Cópia do schema com descrições curtas (primeira frase, com limite). Nomes,
    parâmetros, tipos e campos obrigatórios ficam idênticos.

    O schema entra em toda chamada e é o maior bloco fixo do prompt.
    """

    compacted = []

    for tool in tools:
        function = dict(tool["function"])
        function["description"] = _first_sentence(function.get("description", ""), TOOL_DESCRIPTION_MAX_CHARS)

        parameters = dict(function.get("parameters", {}))
        properties = {}

        for name, spec in parameters.get("properties", {}).items():
            spec = dict(spec)

            if name in SELF_EXPLANATORY_PARAMS:
                # O nome já diz tudo (path, query, url...): a descrição só gasta tokens.
                spec.pop("description", None)
            elif "description" in spec:
                spec["description"] = _first_sentence(spec["description"], PARAM_DESCRIPTION_MAX_CHARS)

            properties[name] = spec

        if properties:
            parameters["properties"] = properties

        function["parameters"] = parameters
        compacted.append({"type": tool.get("type", "function"), "function": function})

    return compacted


# Perfis de tools: o schema entra em toda chamada e é o maior bloco fixo do prompt,
# então o modelo vê só o grupo "base" e os demais conforme a tarefa (ou ao chamá-los).
TOOL_GROUPS = {
    "base": [
        "list_directory",
        "read_file",
        "write_file",
        "replace_in_file",
        "run_command",
        "search_files",
        "check_tools",
        "load_skill",
    ],
    "web": ["web_search", "fetch_url", "download_file"],
    "memory": ["save_memory", "get_memory"],
    "project": ["update_spec_checklist", "get_project_status"],
    "models": [
        "get_model_registry",
        "register_model_candidate",
        "set_smart_candidate_for_benchmark",
        "set_active_smart_model",
    ],
    "skills_authoring": ["propose_skill"],
}

GROUP_ORDER = list(TOOL_GROUPS)

TOOL_TO_GROUP = {name: group for group, names in TOOL_GROUPS.items() for name in names}

GROUP_KEYWORDS = {
    "web": r"\b(pesquis\w*|internet|web|url|https?|download|baix\w*|github|release|documenta\w*|site)\b",
    "memory": r"\b(mem[óo]ria|lembr\w*|memoriz\w*)\b",
    "models": r"\b(registry|smart|candidato|benchmark|quantiz\w*)\b",
    "project": r"\b(checklist|projeto\.md|pend[êe]ncia)\b",
}


def select_tool_groups(prompt: str, is_dev_task: bool = False, phase_text: str = "") -> set:
    """
    Grupos de tools que devem aparecer no schema desta tarefa.

    Sempre "base". Os outros entram por palavras do pedido, no fluxo de desenvolvimento
    (project e memory; models quando a fase trata de modelos) ou quando o modelo chama
    uma tool de um grupo que ainda não estava visível.
    """

    groups = {"base"}
    text = (prompt or "").lower()

    for group, pattern in GROUP_KEYWORDS.items():
        if re.search(pattern, text):
            groups.add(group)

    if is_dev_task:
        groups.update({"project", "memory"})

        if re.search(GROUP_KEYWORDS["models"], (phase_text or "").lower()):
            groups.add("models")

    return groups


def visible_tools(on_smart: bool, groups=None) -> list:
    """
    Schema de tools enviado ao modelo, na ordem fixa dos grupos (ordem estável ajuda o
    cache de prefixo). `groups=None` devolve todos. propose_skill só aparece para o SMART.
    """

    tools = COMPACT_TOOLS if COMPACT_TOOL_SCHEMA else TOOLS
    by_name = {t["function"]["name"]: t for t in tools}

    selected = []

    for group in GROUP_ORDER:
        if group == "skills_authoring":
            if ONLY_SMART_CAN_PROPOSE_SKILLS and not on_smart:
                continue
        elif groups is not None and group not in groups:
            continue

        selected.extend(by_name[name] for name in TOOL_GROUPS[group])

    return selected


COMPACT_TOOLS = compact_tools(TOOLS)


def task_used_web(state) -> bool:
    """True se alguma ferramenta de web/download foi chamada nesta tarefa."""

    return any(
        step.get("type") == "tool_call" and step.get("tool") in WEB_TOOLS
        for step in state.steps
    )


def answer_skipped_tool_calls(messages: list, skipped_calls, reason: str) -> None:
    """
    Responde as tool calls que o Harness decidiu não executar.

    Todo tool_call do assistente precisa de uma mensagem 'tool' correspondente;
    sem isso o histórico fica inconsistente se o modelo for chamado de novo
    (por exemplo, após a escalada para o SMART).
    """

    for skipped in skipped_calls:
        messages.append({
            "role": "tool",
            "tool_name": skipped.function.name,
            "content": str({
                "success": False,
                "error": reason,
                "blocked_by_harness": True,
            }),
        })


# =========================================================
# EXECUÇÃO DO AGENTE
# =========================================================

def agent(prompt: str):

    # =========================================================
    # RESTRIÇÕES DA TAREFA
    # =========================================================

    run_id = new_run_id()
    log("RUN_START", f"run_id={run_id}")

    constraints = TaskConstraints.from_task(prompt)

    log("CONSTRAINTS", str(constraints.summary()))

    # =========================================================
    # ESTADO INICIAL E PROJETO
    # =========================================================

    state = TaskState(prompt)
    progress = extract_project_progress(PROJECT_SPEC)

    if progress["success"]:
        state.set_progress(
            phase=progress["current_phase"],
            next_action=progress["next_action"],
        )

    log("TASK", "Objetivo: " + " ".join(prompt.split())[:160])

    if progress["success"]:
        log(
            "PROJECT",
            f"Fase: {progress['current_phase']} | "
            f"Próxima pendência: {progress['next_action']}",
        )
    else:
        log("PROJECT", f"Erro ao analisar projeto: {progress.get('error')}")

    # =========================================================
    # MODEL ROUTER & CONTEXT MANAGER
    # =========================================================

    router = ModelRouter()
    active_model = router.route_task(prompt, state.current_phase)
    context_mgr = ContextManager(max_context_chars=int(18000 * NUM_CTX / 8192), max_repeated_tool_calls=2)

    log("MODEL_ROUTER", f"Modelo selecionado: {active_model}")

    # =========================================================
    # DECOMPOSIÇÃO DE TAREFA DE DESENVOLVIMENTO
    # =========================================================

    is_dev_task = not prompt.lstrip().startswith(TASK_MARKER) and any(
        kw in prompt.lower()
        for kw in ["continue", "desenvolvimento", "specs/projeto.md", "projeto.md", "checklist"]
    )

    if is_dev_task and progress["success"] and state.next_action:
        effective_goal = (
            f"Executar e validar a pendência imediata '{state.next_action}' "
            f"da {state.current_phase} em specs/projeto.md."
        )
        user_prompt_text = f"""{prompt}

ETAPA IMEDIATA DE DESENVOLVIMENTO DETERMINADA PELO HARNESS:
- Fase: {state.current_phase}
- Pendência a executar: {state.next_action}

Instruções para cumprir esta etapa:
1. Realize o trabalho prático ou verificação necessária para '{state.next_action}'.
2. Se os requisitos da pendência já estiverem satisfeitos e validados (conforme a MEMÓRIA PERSISTENTE e testes), avance para o registro.
3. Quando a etapa estiver concluída e validada na prática, use a ferramenta 'update_spec_checklist' passando:
   item="{state.next_action}", completed=True
   para atualizar formalmente o checklist em specs/projeto.md.
4. Apresente um resumo claro do que foi validado e informe qual é a próxima pendência restante."""
    else:
        effective_goal = prompt
        user_prompt_text = prompt

    # =========================================================
    # RESUMO ESTRUTURADO DO PROJETO
    # =========================================================

    is_numbered_task = prompt.lstrip().startswith(TASK_MARKER)

    enabled_groups = select_tool_groups(
        prompt,
        is_dev_task=is_dev_task,
        phase_text=f"{state.current_phase or ''} {state.next_action or ''}",
    )
    extra_tools = [
        name
        for group in GROUP_ORDER
        if group not in enabled_groups and group != "skills_authoring"
        for name in TOOL_GROUPS[group]
    ]
    extra_tools_note = (
        "Outras ferramentas (chame pelo nome quando precisar): " + ", ".join(extra_tools) + "."
        if extra_tools
        else ""
    )

    memory_store = MemoryStore()
    memory_context = memory_store.format_context(max_chars=MEMORY_PROMPT_MAX_CHARS)

    project_summary = format_project_summary(progress)

    # Só o desenvolvimento do checklist precisa do resumo do projeto e das regras longas;
    # tarefas numeradas e tarefas simples usam o prompt compacto.
    use_compact_prompt = is_numbered_task or not is_dev_task

    if use_compact_prompt:
        project_summary = ""
        project_context = memory_context
    else:
        project_context = f"""
ESTADO DO PROJETO (HARNESS)
{project_summary}

{memory_context}

Orientações:
- Edite com 'replace_in_file'; crie com 'write_file'.
- Valide com 'run_command' executando 'pytest -v' antes de registrar a pendência com 'update_spec_checklist'.
- Não releia o projeto.md inteiro: use 'read_file' com start_line e end_line.
- Use 'get_project_status' uma vez para ver a pendência atual; não repita.
- Seleção de modelo: o Harness exige evidências no registry e na memória.
"""

    # =========================================================
    # CARREGAMENTO DINÂMICO DE SKILLS
    # =========================================================

    matched_skill_names = match_skills(
        prompt,
        current_phase=state.current_phase,
        next_action=state.next_action,
    )

    if is_dev_task:
        if "development" not in matched_skill_names:
            matched_skill_names.append("development")
        if "environment" not in matched_skill_names:
            matched_skill_names.append("environment")
        phase_action_str = f"{state.current_phase or ''} {state.next_action or ''}".lower()
        if any(term in phase_action_str for term in ["modelo", "quantiz", "benchmark", "smart", "registry"]):
            if "models" not in matched_skill_names:
                matched_skill_names.append("models")

    if is_numbered_task:
        # Só o índice: a tarefa já descreve os passos e o modelo pode usar load_skill.
        matched_skill_names = list_skills()

    skills_loaded = []
    for s_name in matched_skill_names:
        s_res = load_skill(s_name)
        if s_res["success"]:
            skills_loaded.append(s_res)
            log("SKILL", f"Skill carregada: {s_res['name']}")

    skill_context = format_skills_context(
        skills_loaded,
        budget_chars=0 if is_numbered_task else SKILLS_BUDGET_CHARS,
    )

    # =========================================================
    # RESTRIÇÕES
    # =========================================================

    constraints_context = (
        f"RESTRIÇÕES: instalações={constraints.allow_install}; "
        f"alterações no sistema={constraints.allow_system_changes}; "
        f"operações destrutivas={constraints.allow_destructive}. Se False, NÃO tente."
    )

    # =========================================================
    # MENSAGENS INICIAIS
    # =========================================================

    if use_compact_prompt:
        system_instructions = f"""
Você é o agente local do projeto {PROJECT_ROOT}. Use as ferramentas para agir; não apenas planeje.

{constraints_context}
{extra_tools_note}

{project_context}

{skill_context}

REGRAS: 1) Faça o que foi pedido, passo a passo. 2) Não repita consultas nem comandos iguais. 3) Se algo falhar 2 vezes, pare e explique o que o usuário deve fazer. 4) Respeite o Permission Manager. 5) Ao terminar, resuma em até 3 linhas.
"""
    else:
        system_instructions = f"""
Você é o agente local autônomo do projeto {PROJECT_ROOT}. Use as ferramentas para ler, editar, pesquisar, executar comandos e atualizar a especificação.

{constraints_context}
{extra_tools_note}

{project_context}

{skill_context}

REGRAS:
1. Aja com as ferramentas; não apenas planeje.
2. Prefira 'replace_in_file' para editar. Arquivo grande: 'read_file' com start_line e end_line.
3. Pesquisa externa: 'web_search' e 'fetch_url'.
4. Valide com 'pytest -v' (run_command).
5. Registre pendências concluídas e validadas com 'update_spec_checklist'.
6. Não repita chamadas iguais; se falhar, mude a abordagem.
7. Respeite o Permission Manager.
8. Ao concluir, resuma e aponte a próxima pendência.
"""

    messages = [
        {
            "role": "system",
            "content": system_instructions.strip(),
        },
        {
            "role": "user",
            "content": user_prompt_text,
        },
    ]

    log(
        "PROMPT_SIZES",
        describe_prompt_sections(
            {
                "system_instructions": system_instructions,
                "user_prompt": user_prompt_text,
                "tools_schema": json.dumps(visible_tools(False, enabled_groups), ensure_ascii=False),
                "detail:constraints": constraints_context,
                "detail:project_summary": project_summary,
                "detail:memory": memory_context,
                "detail:skills": skill_context,
            },
            context_window=NUM_CTX,
        ),
    )


    fixed_tokens = (
        estimate_tokens(system_instructions)
        + estimate_tokens(user_prompt_text)
        + estimate_tokens(json.dumps(visible_tools(False, enabled_groups), ensure_ascii=False))
    )

    if fixed_tokens > NUM_CTX * PROMPT_BUDGET_WARN_RATIO:
        log(
            "PROMPT_TOO_BIG",
            f"prompt fixo estimado em {fixed_tokens} tokens de {NUM_CTX} "
            f"({fixed_tokens / NUM_CTX:.0%}). Sobra pouco espaço para a conversa.",
        )

    # =========================================================
    # LOOP PRINCIPAL
    # =========================================================

    iteration = 0
    consecutive_tool_errors = 0
    stagnation_detector = StagnationDetector()
    tool_memo = ToolMemo()
    response_repeats = RepeatedResponseDetector()

    fast_model = router.get_fast_model() or active_model
    on_smart = active_model != fast_model
    smart_iterations = 0
    smart_progress = False
    escalation_count = 0

    task_number = task_number_from_prompt(prompt)
    acceptance_args = acceptance_command(task_number) if task_number else None
    acceptance_attempts = 0

    while True:

        iteration += 1

        log("ITERATION", f"{iteration}/{MAX_ITERATIONS}")

        if iteration > MAX_ITERATIONS:
            state.fail("Limite máximo de iterações atingido.")
            log("STOP", "Limite máximo de iterações atingido.")
            print("\n[STOP] Limite máximo de iterações atingido.")
            break

        # =====================================================
        # ESCALADA FAST -> SMART E RETORNO SMART -> FAST
        # =====================================================

        if on_smart:
            smart_iterations += 1

            if stagnation_detector.is_stagnated():
                reason = (
                    f"O modelo SMART '{active_model}' também não conseguiu progredir "
                    f"({stagnation_detector.stagnation_cycles} ciclos sem progresso útil)."
                )
                state.needs_human(reason)
                log("NEEDS_HUMAN", reason)
                print(f"\n[NEEDS_HUMAN] {reason}")
                break

            if smart_progress or smart_iterations > SMART_MAX_ITERATIONS:
                why = (
                    "O SMART destravou a etapa; voltando ao modelo FAST."
                    if smart_progress
                    else f"O SMART usou {SMART_MAX_ITERATIONS} iterações sem destravar; voltando ao FAST."
                )
                packet = build_handover_packet(
                    goal=effective_goal,
                    from_model=active_model,
                    to_model=fast_model,
                    reason=why,
                    messages=messages,
                    actions_completed=state.actions_completed,
                    phase=state.current_phase,
                    next_action=state.next_action,
                )
                messages[:] = [messages[0], {"role": "user", "content": packet}]
                log("DE_ESCALATE", why)
                active_model = fast_model
                on_smart = False
                smart_progress = False
                smart_iterations = 0
                consecutive_tool_errors = 0
                stagnation_detector.reset()
                response_repeats.reset()
                state.status = "running"

        if not on_smart:
            # Verificação de escalada (erros técnicos ou estagnação de raciocínio)
            is_stagnated, stag_reason, stag_event = stagnation_detector.check_escalation(
                phase=state.current_phase,
                task=effective_goal,
                fast_model=active_model,
                iteration=iteration,
                last_action=state.last_tool or state.current_step,
            )

            escalate, esc_reason = router.should_escalate(
                consecutive_errors=consecutive_tool_errors,
                iteration=iteration,
                tool_failures=state.failed_tools,
                stagnation_cycles=stagnation_detector.stagnation_cycles,
                max_stagnation_cycles=stagnation_detector.max_stagnation_cycles,
                stagnation_reason=stag_reason,
            )

            if escalate:
                log("ESCALATION_CHECK", esc_reason)
                event = stag_event or stagnation_detector.create_escalation_event(
                    phase=state.current_phase,
                    task=effective_goal,
                    fast_model=active_model,
                    iteration=iteration,
                    last_action=state.last_tool or state.current_step or "Nenhuma ação recente",
                    reason=esc_reason,
                )
                state.escalate_to_smart(event, reason=esc_reason)
                log("ESCALATE_TO_SMART", json.dumps(state.escalation_event, ensure_ascii=False))
                print(f"\n[ESCALATE_TO_SMART] {esc_reason}")

                # Verificação determinística da disponibilidade do SMART
                is_available, smart_reason, smart_diag = router.check_smart_availability()
                smart_diag.update({
                    "fast_model": active_model,
                    "escalation_reason": esc_reason,
                    "phase": state.current_phase,
                    "task": effective_goal,
                })

                if is_available:
                    escalation_count += 1

                    if escalation_count > MAX_ESCALATIONS:
                        reason = (
                            f"A tarefa já foi escalada {MAX_ESCALATIONS} vezes sem destravar. "
                            "É preciso uma decisão ou ação do usuário."
                        )
                        state.needs_human(reason)
                        log("NEEDS_HUMAN", reason)
                        print(f"\n[NEEDS_HUMAN] {reason}")
                        break

                    smart_model = router.get_smart_model()
                    state.resolve_escalation_smart_available(smart_diag, reason=smart_reason)
                    log("SMART_AVAILABLE", json.dumps(smart_diag, ensure_ascii=False))
                    print(f"\n[SMART_AVAILABLE] {smart_reason}")

                    # O SMART recebe um resumo curto, não o histórico (e os loops) do FAST.
                    packet = build_handover_packet(
                        goal=effective_goal,
                        from_model=active_model,
                        to_model=smart_model,
                        reason=esc_reason,
                        messages=messages,
                        actions_completed=state.actions_completed,
                        phase=state.current_phase,
                        next_action=state.next_action,
                    )
                    messages[:] = [messages[0], {"role": "user", "content": packet}]

                    fast_model = active_model
                    active_model = smart_model
                    on_smart = True
                    smart_progress = False
                    smart_iterations = 0
                    consecutive_tool_errors = 0
                    stagnation_detector.reset()
                    response_repeats.reset()
                    state.status = "running"
                    log("ESCALATED", f"Tarefa entregue ao modelo especialista SMART: {active_model}")
                else:
                    state.resolve_escalation_smart_unavailable(smart_diag, reason=smart_reason)
                    log("SMART_UNAVAILABLE", json.dumps(smart_diag, ensure_ascii=False))
                    print(f"\n[SMART_UNAVAILABLE] {smart_reason}")
                    print("\n[PROXIMA_CAPACIDADE] Selecionar/preparar modelo SMART (Model Scout).")
                    log("STOP", f"Escalonamento para SMART: SMART indisponível ({smart_reason}). Próxima capacidade: selecionar/preparar SMART.")
                    print(f"\n[STOP] Escalonamento para SMART: SMART indisponível. Próxima capacidade necessária: selecionar/preparar SMART.")
                    break

        log("MODEL", active_model)

        # Prepara mensagens através do ContextManager (compactação automática se necessário)
        prepared_messages = context_mgr.prepare_messages(messages)

        try:
            call_started = time.monotonic()

            response = client.chat(
                model=active_model,
                messages=prepared_messages,
                tools=visible_tools(on_smart, enabled_groups),
                think=THINK,
                options={"num_ctx": NUM_CTX},
            )

            call_seconds = time.monotonic() - call_started
            speed = tokens_per_second(
                response.eval_count or 0,
                getattr(response, "eval_duration", None),
                call_seconds,
            )

            log(
                "TOKENS",
                f"input={response.prompt_eval_count or 0} | "
                f"output={response.eval_count or 0} | "
                f"total={(response.prompt_eval_count or 0) + (response.eval_count or 0)} | "
                f"seconds={call_seconds:.1f} | "
                f"tok_s={'-' if speed is None else format(speed, '.1f')}"
            )

            pressure = context_pressure(response.prompt_eval_count or 0, NUM_CTX)

            if pressure != "ok":
                log(
                    "CONTEXT_" + pressure.upper(),
                    f"prompt={response.prompt_eval_count} de {NUM_CTX} tokens. "
                    "O Ollama pode estar descartando o início da conversa; pedindo compactação.",
                )
                context_mgr.request_compaction()

        except Exception as e:
            state.fail(f"Erro ao consultar o modelo: {e}")
            log("STOP", f"Erro ao consultar o modelo: {e}")
            print(f"\n[ERROR] Falha ao consultar o modelo: {e}")
            break

        # =====================================================
        # MODELO SOLICITOU FERRAMENTA
        # =====================================================

        if response.message.tool_calls:

            task_cancelled = False

            # Registra mensagem do assistente com tool_calls no histórico
            messages.append(response.message)

            for call_index, call in enumerate(response.message.tool_calls):

                name = call.function.name
                arguments = call.function.arguments

                state.set_progress(
                    current_step=f"Executando ferramenta: {name}",
                    next_action=f"Executar {name}",
                )

                log("STATE", f"step={state.current_step}")
                log("TOOL", f"{name} | {arguments}")

                group = TOOL_TO_GROUP.get(name)
                if group and group != "skills_authoring" and group not in enabled_groups:
                    enabled_groups.add(group)
                    log("TOOL_GROUP_ENABLED", f"{group} (chamada a {name})")

                state.start_tool(name, arguments)

                # Prevenção de loop ANTES da execução
                is_loop, loop_msg = context_mgr.check_loop(name, arguments)
                if is_loop:
                    result = {
                        "success": False,
                        "error": loop_msg,
                        "blocked_by_harness": True,
                        "loop_blocked": True,
                    }
                    log("LOOP_BLOCKED", loop_msg)
                else:
                    # Verifica restrições
                    constraint_error = check_task_constraint(name, arguments, constraints)
                    if constraint_error is not None:
                        result = constraint_error
                        log("CONSTRAINT", result["error"])
                    elif name == "propose_skill" and ONLY_SMART_CAN_PROPOSE_SKILLS and not on_smart:
                        result = {
                            "success": False,
                            "error": "Somente o modelo SMART pode propor Skills. Registre a necessidade e continue a tarefa.",
                            "blocked_by_harness": True,
                            "tool_error": True,
                        }
                        log("SKILL_PROPOSAL_DENIED", "propose_skill fora do modelo SMART")
                    else:
                        if name == "propose_skill" and isinstance(arguments, dict):
                            # O Harness, e não o modelo, informa se houve uso da web.
                            arguments = {**arguments, "used_web": task_used_web(state)}

                        result = tool_memo.lookup(name, arguments)

                        if result is not None:
                            log("TOOL_CACHE_HIT", name)
                        else:
                            result = execute_tool(name, arguments)
                            tool_memo.record(name, arguments, result)

                state.finish_tool(name, result)

                # Avaliação determinística de progresso real vs estagnação
                state_snapshot = {
                    "current_phase": state.current_phase,
                    "next_action": state.next_action,
                }
                is_prog = stagnation_detector.record_action(
                    name=name,
                    arguments=arguments,
                    result=result,
                    current_state=state_snapshot,
                )
                if is_prog:
                    if on_smart:
                        smart_progress = True
                    log("PROGRESS_DETECTED", f"Progresso útil detectado na ferramenta: {name}")
                elif result.get("success"):
                    log("STAGNATION_CYCLE", f"Ação sem progresso útil: {name} (ciclos={stagnation_detector.stagnation_cycles})")

                # Verificação de loop no ContextManager
                loop_warning = context_mgr.record_tool_call(name, arguments, result)
                if loop_warning and isinstance(result, dict):
                    result["harness_warning"] = loop_warning
                    log("LOOP_WARNING", loop_warning)

                # Cancelamento pelo usuário
                if result.get("cancelled"):
                    reason = result.get("error", "Execução cancelada pelo usuário.")
                    state.cancel(reason)
                    log("RESULT", f"{name} | CANCELADO")
                    log("CANCELLED", reason)
                    print("\n[AGENT] Tarefa cancelada pelo usuário.")
                    task_cancelled = True
                    answer_skipped_tool_calls(
                        messages,
                        response.message.tool_calls[call_index + 1:],
                        "Tarefa cancelada pelo usuário.",
                    )
                    break

                # Sucesso vs Falha
                if result.get("success"):
                    consecutive_tool_errors = 0
                    state.action_completed(f"{name}: {arguments}")
                    state.set_progress(
                        current_step=f"{name} concluído",
                        next_action="Analisar resultado e decidir próxima ação",
                    )
                    log("RESULT", f"{name} | OK")

                    # Se atualizou o checklist do projeto com sucesso, reflete no estado
                    if name == "update_spec_checklist":
                        new_prog = extract_project_progress(PROJECT_SPEC)
                        if new_prog.get("success"):
                            old_action = state.next_action
                            new_action = new_prog.get("next_action")
                            new_phase = new_prog.get("current_phase")
                            state.set_progress(
                                phase=new_phase,
                                next_action=new_action,
                            )
                            log(
                                "PROGRESS_ADVANCED",
                                f"Fase: {new_phase} | Próxima: {new_action}",
                            )
                            if new_action != old_action or new_phase != state_snapshot.get("current_phase"):
                                stagnation_detector.reset()
                            # Se a etapa avançou, atualiza effective_goal e orienta o modelo
                            if is_dev_task and new_action and new_action != old_action:
                                effective_goal = (
                                    f"Executar e validar a pendência imediata '{new_action}' "
                                    f"da {new_phase} em specs/projeto.md."
                                )
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"[HARNESS UPDATE] Checklist atualizado: a etapa '{arguments.get('item')}' foi registrada como concluída. "
                                        f"A NOVA etapa imediata determinada pelo Harness agora é: '{new_action}' (Fase: {new_phase}). "
                                        f"ATENÇÃO: NÃO repita a ação de '{arguments.get('item')}'. Prossiga imediatamente com a pendência ativa: '{new_action}'."
                                    ),
                                })
                else:
                    consecutive_tool_errors += 1
                    error = result.get("error", "erro desconhecido")
                    state.set_progress(
                        current_step=f"{name} falhou",
                        next_action="Analisar erro e decidir recuperação",
                    )
                    log("RESULT", f"{name} | FAIL | {error}")

                # Resultado da ferramenta volta para o modelo
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": str(result),
                })

                if stagnation_detector.is_stagnated():
                    log("STAGNATION_THRESHOLD_REACHED", f"Limite de estagnação atingido ({stagnation_detector.stagnation_cycles} ciclos). Interrompendo para escalonamento.")
                    answer_skipped_tool_calls(
                        messages,
                        response.message.tool_calls[call_index + 1:],
                        "Não executada: o Harness interrompeu o lote por estagnação.",
                    )
                    break

            if task_cancelled:
                break

            continue

        # =========================================================
        # MODELO RESPONDEU SEM FERRAMENTA (TEXTO)
        # =========================================================

        messages.append(response.message)

        content = response.message.content or getattr(response.message, "thinking", "") or ""

        log("RESPONSE", content)
        state.model_response(content)

        print("\n[AGENT]")
        print(content)

        if response_repeats.check(content):
            reason = (
                "O modelo está repetindo a mesma resposta sem avançar; "
                "a tarefa provavelmente depende de uma ação sua (senha, decisão ou aprovação)."
            )
            state.needs_human(reason)
            log("NEEDS_HUMAN", reason)
            print(f"\n[NEEDS_HUMAN] {reason}")
            break

        # Avaliação de conclusão rigorosa controlada pelo Harness
        if acceptance_args is not None:
            # Tarefa numerada com teste de aceite: quem decide é o teste, não um LLM.
            passed, acceptance_output = run_acceptance(acceptance_args)
            acceptance_attempts += 1
            log(
                "ACCEPTANCE",
                f"tentativa {acceptance_attempts}/{MAX_ACCEPTANCE_ATTEMPTS} | {'passou' if passed else 'falhou'}",
            )

            if passed:
                completion = {
                    "status": "complete",
                    "reason": "O teste de aceite da tarefa passou (verificação executável do Harness).",
                }
            elif acceptance_attempts >= MAX_ACCEPTANCE_ATTEMPTS:
                reason = (
                    f"A tarefa não passou no teste de aceite depois de {acceptance_attempts} tentativas. "
                    f"Última saída: {acceptance_output[-400:]}"
                )
                state.needs_human(reason)
                log("NEEDS_HUMAN", reason)
                print(f"\n[NEEDS_HUMAN] {reason}")
                break
            else:
                completion = {
                    "status": "continue",
                    "reason": (
                        "O teste de aceite FALHOU. Saída (final):\n"
                        f"{acceptance_output}\n"
                        "Corrija SOMENTE o que o teste aponta, sem refazer o que já está certo, e responda quando terminar."
                    ),
                }
        elif state.last_tool_success is False:
            # Se for repetição/loop bloqueado consecutivo sem recuperação
            last_err = str(getattr(state, "last_failure_reason", "") or "")
            if consecutive_tool_errors >= 2 and ("bloqueada para evitar loops" in last_err or "loop_blocked" in last_err):
                block_reason = (
                    f"Execução interrompida pelo Harness: modelo entrou em loop repetitivo na ferramenta '{state.last_tool}'. "
                    f"Motivo: {last_err}"
                )
                state.block(block_reason)
                log("BLOCKED", block_reason)
                print(f"\n[BLOCKED] {block_reason}")
                break

            completion = {
                "status": "continue",
                "reason": build_continuation_reason(
                    current_phase=state.current_phase,
                    next_action=state.next_action,
                    base_reason=(
                        f"A última ação de ferramenta ({state.last_tool}) falhou ou foi bloqueada pelo Harness. "
                        "A tarefa não pode ser concluída com erro pendente. Ajuste a abordagem e prossiga."
                    ),
                ),
            }
        elif is_dev_task and state.next_action:
            # Tarefa contínua de desenvolvimento com pendências restantes no projeto
            completion = {
                "status": "continue",
                "reason": build_continuation_reason(
                    current_phase=state.current_phase,
                    next_action=state.next_action,
                ),
            }
        else:
            completion = check_completion(
                model=active_model,
                task=effective_goal,
                response=content,
                tool_calls=state.tool_calls,
                successful_tools=state.successful_tools,
                failed_tools=state.failed_tools,
                actions_completed=state.actions_completed,
                last_tool_success=state.last_tool_success,
                last_failure_reason=state.last_failure_reason,
            )

        log("COMPLETION", f"{completion['status']} | {completion['reason']}")

        if completion["status"] == "complete":
            state.complete()
            log("DONE", completion["reason"])
            print(f"\n[COMPLETION] {completion['reason']}")
            break

        # Tarefa ainda não concluída
        state.status = "running"
        stagnation_detector.record_text_cycle(content)
        state.set_progress(
            current_step=f"Executando pendência: {state.next_action}" if state.next_action else "Tarefa ainda não concluída",
            next_action=state.next_action or "Executar próxima ação necessária",
        )

        log("CONTINUE", completion["reason"])

        if acceptance_args is not None:
            # Mensagem curta: repetir a tarefa inteira a cada tentativa gastaria o contexto.
            messages.append({"role": "user", "content": completion["reason"]})
            continue

        messages.append({
            "role": "user",
            "content": f"""
A tarefa ainda não foi concluída.
Status do Harness:
{completion['reason']}

Etapa imediata atual: {effective_goal}
Orientações:
1. NÃO repita comandos ou verificações já executados com sucesso recentemente.
2. Se a ferramenta anterior falhou ou foi bloqueada pelo Harness, NÃO insista na mesma chamada com os mesmos argumentos.
3. Se desejar confirmar o estado e a próxima ação do projeto, use 'get_project_status'.
4. Realize o trabalho prático da pendência atual e, após validar, registre-a com 'update_spec_checklist'.
"""
        })

    # =========================================================
    # PERSISTÊNCIA DO TASK STATE
    # =========================================================

    summary = state.summary()

    try:
        tasks_dir = TASKS_DIR
        tasks_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        task_file = tasks_dir / f"task_{timestamp}.json"
        task_file.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log("TASK_SAVED", str(task_file))
    except Exception as e:
        log("TASK_SAVE_ERROR", str(e))

    log(
        "STATE",
        f"status={summary['status']} | "
        f"phase={summary['current_phase']} | "
        f"step={summary['current_step']} | "
        f"next={summary['next_action']} | "
        f"tools={summary['tool_calls']} | "
        f"success={summary['successful_tools']} | "
        f"failed={summary['failed_tools']}"
    )

    print("\n[STATE]")
    print(f"Status: {summary['status']}")
    print(f"Fase: {summary['current_phase']}")
    print(f"Passo atual: {summary['current_step']}")
    print(f"Próxima ação: {summary['next_action']}")
    print(f"Ferramentas: {summary['tool_calls']}")
    print(f"Sucessos: {summary['successful_tools']}")
    print(f"Falhas: {summary['failed_tools']}")


# =========================================================
# ENTRYPOINT
# =========================================================

def resolve_prompt(text: str) -> str | None:
    """
    Converte '@nome' no conteúdo de prompts/nome.md. Texto comum passa direto.
    Retorna None (após avisar) quando o prompt salvo não existe.
    """

    text = text.strip()

    number = find_task_number(text)

    if number is not None:
        ok, content = build_task_prompt(number, text)

        if not ok:
            print(content)
            return None

        print(f"Carregando a tarefa {number:02d} (e o progresso salvo, se houver).")
        return content

    if not text.startswith("@"):
        return text

    ok, content = load_prompt(text[1:])

    if not ok:
        print(content)
        return None

    return content


def interactive_loop(read=input) -> None:
    """
    Loop de tarefas do terminal. Ctrl+C durante uma tarefa a interrompe (ela fica
    registrada no log) e volta ao prompt, em vez de fechar o programa com erro.
    """

    saved = ", ".join(f"@{name}" for name in list_prompts())

    if saved:
        print(f"Prompts salvos: {saved}")

    numbered = ", ".join(f"{n}" for n, _ in list_tasks())

    if numbered:
        print(f"Tarefas numeradas: {numbered}  (ex.: dê continuidade à tarefa 2)")

    while True:
        try:
            typed = read("\nTarefa (ENTER vazio para sair): ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not typed.strip():
            break

        prompt = resolve_prompt(typed)

        if prompt is None:
            continue

        try:
            agent(prompt)
        except KeyboardInterrupt:
            log("INTERRUPTED", "tarefa interrompida pelo usuário (Ctrl+C)")
            print("\n[INTERROMPIDO] Tarefa interrompida. Você pode pedir outra.")


if __name__ == "__main__":
    ensure_utf8_console()
    interactive_loop()
