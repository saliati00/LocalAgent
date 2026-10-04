import json
from pathlib import Path
from core.memory.store import MemoryStore


REGISTRY_PATH = Path("/home/bruno/local-agent/models/registry.json")
_memory_store = MemoryStore()


def _load_registry_data() -> dict:
    if not REGISTRY_PATH.exists():
        return {
            "active_fast_model": None,
            "active_smart_model": None,
            "models": {},
        }
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "active_fast_model": None,
            "active_smart_model": None,
            "models": {},
        }


def _save_registry_data(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_model_registry(role: str = "") -> dict:
    """
    Consulta os modelos cadastrados no Model Registry (models/registry.json).
    Permite filtrar pelo papel do modelo ('fast', 'smart') ou listar todos.

    Papéis arquiteturais:
    - 'fast': modelo operador rápido
    - 'smart': modelo especialista (o tamanho é atributo factual, não requisito do papel)
    """
    data = _load_registry_data()
    models = data.get("models", {})

    if role and role.strip():
        r = role.strip().lower()
        filtered = {k: v for k, v in models.items() if v.get("role", "").lower() == r}
    else:
        filtered = models

    return {
        "success": True,
        "active_fast_model": data.get("active_fast_model"),
        "active_smart_model": data.get("active_smart_model"),
        "models_count": len(filtered),
        "models": filtered,
    }


def register_model_candidate(
    name: str,
    role: str,
    backend: str,
    size_gb: float,
    vram_gb: float,
    description: str,
    justification: str,
    context_window: int = 32768,
) -> dict:
    """
    Registra ou atualiza um modelo candidato no Model Registry e na Memória Persistente.
    A justificativa técnica de compatibilidade com o hardware é obrigatória.

    O papel ('fast' ou 'smart') é determinado pela função do modelo no sistema,
    não pelo seu tamanho. Um modelo SMART pode ter qualquer número de parâmetros.

    Status inicial: 'candidate' — distinto de 'selected_for_benchmark' e 'adopted'.
    """
    if not name or not name.strip():
        return {"success": False, "error": "Nome do modelo é obrigatório."}

    if not justification or not justification.strip():
        return {
            "success": False,
            "error": "Justificativa técnica é obrigatória (especifique compatibilidade de VRAM, offload e função).",
        }

    clean_name = name.strip()
    data = _load_registry_data()

    if "models" not in data:
        data["models"] = {}

    model_entry = {
        "name": clean_name,
        "role": role.strip().lower(),
        "backend": backend.strip().lower(),
        "size_gb": float(size_gb),
        "vram_gb": float(vram_gb),
        "context_window": int(context_window),
        "status": "candidate",
        "description": description.strip(),
        "justification": justification.strip(),
    }

    data["models"][clean_name] = model_entry
    _save_registry_data(data)

    # Persiste também na memória permanente do agente
    _memory_store.set(
        category="decisions",
        key=f"candidate_{clean_name}",
        value=clean_name,
        description=f"Candidato {role}: {justification.strip()}",
    )

    return {
        "success": True,
        "message": f"Modelo '{clean_name}' registrado com sucesso como candidato {role}.",
        "model": model_entry,
    }


def set_smart_candidate_for_benchmark(model_name: str, rationale: str = "") -> dict:
    """
    Marca um modelo candidato como selecionado para benchmark.

    'selected_for_benchmark' NÃO significa 'adopted'.
    O modelo ainda precisa passar pelo benchmark e ser formalmente adotado
    via set_active_smart_model() para se tornar o SMART ativo.

    Fluxo de estados:
    candidate → selected_for_benchmark → adopted | rejected
    """
    if not model_name or not model_name.strip():
        return {"success": False, "error": "Nome do modelo é obrigatório."}

    clean_name = model_name.strip()
    data = _load_registry_data()

    if "models" not in data or clean_name not in data["models"]:
        return {
            "success": False,
            "error": f"Modelo '{clean_name}' não encontrado no registry. Registre-o primeiro com 'register_model_candidate'.",
        }

    data["models"][clean_name]["status"] = "selected_for_benchmark"
    _save_registry_data(data)

    desc = rationale.strip() if rationale else f"Modelo SMART selecionado para benchmark: {clean_name}"
    _memory_store.set(
        category="decisions",
        key=f"benchmark_candidate_{clean_name}",
        value=clean_name,
        description=desc,
    )

    return {
        "success": True,
        "model": clean_name,
        "status": "selected_for_benchmark",
        "message": (
            f"Modelo '{clean_name}' marcado como selecionado para benchmark. "
            "Use set_active_smart_model() após validação para adotá-lo formalmente."
        ),
    }


def set_active_smart_model(model_name: str, justification: str = "") -> dict:
    """
    Adota formalmente um modelo como o modelo SMART ativo no Model Registry.

    PRÉ-REQUISITO OBRIGATÓRIO: o modelo deve estar com status 'selected_for_benchmark'
    no registry antes de poder ser adotado. Tentativas de adotar um modelo com
    status 'candidate' (ou qualquer outro que não 'selected_for_benchmark') são
    rejeitadas deterministicamente — independentemente do que o LLM solicitar.

    Fluxo válido obrigatório:
        candidate → selected_for_benchmark → adopted (active_smart_model)

    Para marcar um candidato para benchmark, use set_smart_candidate_for_benchmark().
    """
    if not model_name or not model_name.strip():
        return {"success": False, "error": "Nome do modelo é obrigatório."}

    clean_name = model_name.strip()
    data = _load_registry_data()

    # ── Guard determinístico de lifecycle ──────────────────────────────────
    # Rejeita a adoção se o modelo não passou por 'selected_for_benchmark'.
    # O registry pode não conter o modelo (ex.: modelo externo não registrado);
    # nesse caso também rejeitamos, pois não há evidência de seleção formal.
    model_entry = data.get("models", {}).get(clean_name)

    if model_entry is None:
        return {
            "success": False,
            "error": (
                f"Modelo '{clean_name}' não encontrado no registry. "
                "Registre-o com 'register_model_candidate' e selecione-o para benchmark "
                "com 'set_smart_candidate_for_benchmark' antes de adotar."
            ),
        }

    current_status = model_entry.get("status", "")
    if current_status != "selected_for_benchmark":
        return {
            "success": False,
            "error": (
                f"Lifecycle violado: o modelo '{clean_name}' está com status '{current_status}', "
                "mas a adoção exige status 'selected_for_benchmark'. "
                "Execute 'set_smart_candidate_for_benchmark' antes de adotar. "
                "Fluxo obrigatório: candidate → selected_for_benchmark → adopted."
            ),
        }
    # ── Fim do guard ───────────────────────────────────────────────────────

    data["active_smart_model"] = clean_name
    data["models"][clean_name]["status"] = "adopted"
    _save_registry_data(data)

    # Persiste na memória do agente
    desc = justification.strip() if justification else f"Modelo SMART adotado: {clean_name}"
    _memory_store.set(
        category="decisions",
        key="active_smart_model",
        value=clean_name,
        description=desc,
    )

    return {
        "success": True,
        "active_smart_model": clean_name,
        "message": f"Modelo SMART ativo atualizado para '{clean_name}'.",
    }


# =========================================================
# FAST MODEL LIFECYCLE
# candidate → selected_for_benchmark → adopted
#
# Infraestrutura equivalente à do SMART, para garantir que
# o papel FAST passe pelo mesmo processo formal nas Fases 7/8.
# O qwen3:8b instalado permanece como bootstrap atual e NÃO
# é automaticamente adotado por essas funções.
# =========================================================


def set_fast_candidate_for_benchmark(model_name: str, rationale: str = "") -> dict:
    """
    Marca um modelo FAST candidato como selecionado para benchmark.

    'selected_for_benchmark' NÃO significa 'adopted'.
    O modelo ainda precisa passar pelo benchmark e ser formalmente adotado
    via set_active_fast_model() para se tornar o FAST ativo.

    Fluxo de estados:
    candidate → selected_for_benchmark → adopted | rejected

    NOTA: O qwen3:8b atual possui status 'installed' (bootstrap sem lifecycle
    formal). Este método é para uso nas Fases 7/8 com candidatos formais.
    """
    if not model_name or not model_name.strip():
        return {"success": False, "error": "Nome do modelo é obrigatório."}

    clean_name = model_name.strip()
    data = _load_registry_data()

    if "models" not in data or clean_name not in data["models"]:
        return {
            "success": False,
            "error": (
                f"Modelo '{clean_name}' não encontrado no registry. "
                "Registre-o primeiro com 'register_model_candidate'."
            ),
        }

    data["models"][clean_name]["status"] = "selected_for_benchmark"
    _save_registry_data(data)

    desc = rationale.strip() if rationale else f"Modelo FAST selecionado para benchmark: {clean_name}"
    _memory_store.set(
        category="decisions",
        key=f"fast_benchmark_candidate_{clean_name}",
        value=clean_name,
        description=desc,
    )

    return {
        "success": True,
        "model": clean_name,
        "status": "selected_for_benchmark",
        "message": (
            f"Modelo FAST '{clean_name}' marcado como selecionado para benchmark. "
            "Use set_active_fast_model() após validação para adotá-lo formalmente."
        ),
    }


def set_active_fast_model(model_name: str, justification: str = "") -> dict:
    """
    Adota formalmente um modelo como o modelo FAST ativo no Model Registry.

    Deve ser chamado apenas após benchmark e validação — representa adoção
    formal, não seleção preliminar. Para marcar um candidato para benchmark,
    use set_fast_candidate_for_benchmark().

    Fluxo: candidate → selected_for_benchmark → adopted (active_fast_model)

    NOTA: O qwen3:8b atual possui status 'installed' (bootstrap sem lifecycle
    formal). Esta função é para uso nas Fases 7/8 com candidatos formais.
    """
    if not model_name or not model_name.strip():
        return {"success": False, "error": "Nome do modelo é obrigatório."}

    clean_name = model_name.strip()
    data = _load_registry_data()

    data["active_fast_model"] = clean_name

    # Atualiza status para 'adopted' se o modelo estiver no registry
    if "models" in data and clean_name in data["models"]:
        data["models"][clean_name]["status"] = "adopted"

    _save_registry_data(data)

    # Persiste na memória do agente
    desc = justification.strip() if justification else f"Modelo FAST adotado: {clean_name}"
    _memory_store.set(
        category="decisions",
        key="active_fast_model",
        value=clean_name,
        description=desc,
    )

    return {
        "success": True,
        "active_fast_model": clean_name,
        "message": f"Modelo FAST ativo atualizado para '{clean_name}'.",
    }
