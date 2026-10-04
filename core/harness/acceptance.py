import json
from pathlib import Path


REGISTRY_PATH = Path("/home/bruno/local-agent/models/registry.json")
MEMORY_STORE_PATH = Path("/home/bruno/local-agent/memory/store.json")

# Modelos conhecidos que são alucinações comuns (não existem oficialmente)
INVALID_HALLUCINATED_MODELS = {
    "llama3:14b",  # Família Llama 3 não possui variante oficial 14B
}


def _is_valid_smart_candidate(candidate_name: str) -> tuple[bool, str | None]:
    """
    Verifica se o nome do candidato SMART não é um modelo alucinado/inexistente.
    Retorna (True, None) se válido, ou (False, motivo) se inválido.
    """
    clean = candidate_name.lower().strip()
    for hallucinated in INVALID_HALLUCINATED_MODELS:
        if clean == hallucinated or clean.startswith(hallucinated):
            return False, (
                f"O modelo '{candidate_name}' é inválido ou não existe oficialmente. "
                f"Modelos alucinados conhecidos: {', '.join(sorted(INVALID_HALLUCINATED_MODELS))}."
            )
    return True, None


def check_checklist_acceptance(
    item: str,
    completed: bool,
    project_spec_path: str = "/home/bruno/local-agent/specs/projeto.md",
) -> tuple[bool, str | None]:
    """
    Verifica se os critérios de aceitação e evidências formais do Harness
    foram satisfeitos antes de permitir a alteração do checklist em specs/projeto.md.

    Retorna (True, None) se aprovado pelo Harness, ou (False, motivo_da_rejeição).
    """
    if not completed:
        # Desmarcar pendência é sempre permitido
        return True, None

    item_lower = (item or "").strip().lower()

    # =========================================================
    # REGRA: ESCOLHER MODELO SMART CANDIDATO
    # =========================================================
    # Acionada por qualquer variante de "escolher modelo smart candidato"
    # (inclui redações legadas como "escolher modelo 14b candidato")
    is_smart_candidate_selection = (
        ("escolher modelo smart" in item_lower and "candidato" in item_lower)
        or ("escolher modelo" in item_lower and "candidato" in item_lower and "smart" in item_lower)
        # legado: aceitar item antigo que ainda menciona 14b, mas validar como SMART
        or ("escolher modelo 14b candidato" in item_lower)
        or ("modelo smart candidato" in item_lower)
    )

    if is_smart_candidate_selection:
        # 1. Verifica se o registry existe
        if not REGISTRY_PATH.exists():
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                "O arquivo 'models/registry.json' não foi encontrado. "
                "Registre o modelo candidato utilizando 'register_model_candidate'."
            )

        try:
            registry_data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Erro ao ler registry de modelos: {e}"

        models = registry_data.get("models", {})

        # 2. Identifica candidatos com role SMART
        smart_candidates = {
            name: info
            for name, info in models.items()
            if info.get("role", "").lower() == "smart"
        }

        # 3. Exige pelo menos 2 candidatos avaliados
        if len(smart_candidates) < 2:
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                f"Apenas {len(smart_candidates)} candidato(s) SMART registrado(s). "
                "É necessário avaliar pelo menos 2 candidatos SMART antes de tomar uma decisão. "
                "Registre mais candidatos com 'register_model_candidate'."
            )

        # 4. Verifica que candidatos possuem identificação válida e não são alucinações
        for cand_name in smart_candidates:
            valid, invalid_reason = _is_valid_smart_candidate(cand_name)
            if not valid:
                return False, (
                    f"Critérios de aceitação rejeitados pelo Harness: {invalid_reason}"
                )

        # 5. Verifica se há evidências de decisão registrada (rationale + alternativas)
        has_registry_justification = any(
            bool(info.get("justification"))
            for info in smart_candidates.values()
        )

        # 6. Verifica evidência de decisão na memória persistente
        has_memory_decision = False
        if MEMORY_STORE_PATH.exists():
            try:
                mem_data = json.loads(MEMORY_STORE_PATH.read_text(encoding="utf-8"))
                decisions = mem_data.get("decisions", {})
                for k, v in decisions.items():
                    val_str = str(v.get("value", "")).lower()
                    desc_str = str(v.get("description", "")).lower()
                    key_lower = k.lower()
                    if (
                        "smart" in key_lower
                        or "candidato" in key_lower
                        or "smart" in val_str
                        or "candidato" in desc_str
                        or "modelo" in key_lower
                    ):
                        has_memory_decision = True
                        break
            except Exception:
                pass

        if not (has_registry_justification or has_memory_decision):
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                "A escolha do candidato SMART ainda não possui justificativa técnica registrada. "
                "É obrigatório registrar a justificativa técnica (compatibilidade de hardware, "
                "quantização considerada, fit de VRAM, estimativa de desempenho) via "
                "'register_model_candidate' e/ou na memória persistente via "
                "'save_memory(category=\"decisions\", ...)'."
            )

        # 7. Verifica se pelo menos um candidato tem atributos de hardware avaliados
        has_hardware_fit = any(
            info.get("vram_gb") and info.get("size_gb")
            for info in smart_candidates.values()
        )
        if not has_hardware_fit:
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                "Nenhum candidato SMART possui informações de hardware registradas "
                "(vram_gb e size_gb). Registre o fit de hardware para cada candidato."
            )

        # Todos os critérios satisfeitos — seleção SMART válida
        return True, None

    # =========================================================
    # REGRA: BAIXAR MODELO
    # =========================================================
    if item_lower == "baixar modelo" or (item_lower.startswith("baixar") and "modelo" in item_lower):
        # 1. Lê o registry para identificar o candidato SMART em selected_for_benchmark
        if not REGISTRY_PATH.exists():
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                "Registry não encontrado. Não é possível verificar o candidato SMART selecionado."
            )

        try:
            registry_data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Erro ao ler registry de modelos: {e}"

        models = registry_data.get("models", {})

        # 2. Identifica o candidato SMART com status selected_for_benchmark
        selected_candidates = [
            name
            for name, info in models.items()
            if info.get("role", "").lower() == "smart"
            and info.get("status") == "selected_for_benchmark"
        ]

        if not selected_candidates:
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                "Nenhum modelo SMART com status 'selected_for_benchmark' encontrado no registry. "
                "Execute 'set_smart_candidate_for_benchmark' antes de tentar baixar o modelo."
            )

        # Usa o primeiro candidato selecionado (deve haver exatamente um)
        target_model = selected_candidates[0]

        # 3. Verifica se esse modelo específico está instalado no Ollama
        import subprocess
        try:
            res = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            installed_output = res.stdout.strip()
        except Exception as e:
            return False, f"Erro ao verificar modelos no Ollama: {e}"

        # Verifica se o nome do candidato selecionado aparece na saída do ollama list
        # Normaliza: ignora diferenças de case e tag :latest
        target_normalized = target_model.lower().split(":")[0]
        installed_lines = installed_output.splitlines()[1:]  # pula o cabeçalho
        found = any(
            target_normalized in line.lower()
            for line in installed_lines
            if line.strip()
        )

        if not found:
            return False, (
                "Critérios de aceitação rejeitados pelo Harness: "
                f"O modelo SMART selecionado para benchmark ('{target_model}') "
                "não foi encontrado na lista de modelos instalados ('ollama list'). "
                "Realize o download do modelo selecionado antes de marcar este item."
            )

        return True, None

    # Critérios padrão para outros itens (permitido por padrão até haver regra dedicada)
    return True, None
