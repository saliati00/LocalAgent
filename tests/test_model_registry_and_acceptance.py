import json
import pytest
from pathlib import Path

from core.harness.acceptance import check_checklist_acceptance
from core.skills.loader import match_skills
from tools.models import (
    get_model_registry,
    register_model_candidate,
    set_active_smart_model,
    set_smart_candidate_for_benchmark,
    set_fast_candidate_for_benchmark,
    set_active_fast_model,
)


# =========================================================
# SKILL LOADER — sem dependência de "14b" como gatilho arquitetural
# =========================================================

def test_match_skills_smart_phase_triggers_models():
    """Skill 'models' deve ser acionada por conceitos SMART, não pela string '14b'."""
    skills = match_skills(
        "Continue a tarefa",
        current_phase="FASE 2 — SMART — Seleção do Modelo Especialista",
        next_action="Escolher modelo SMART candidato",
    )
    assert "models" in skills
    assert "development" in skills


def test_match_skills_no_14b_required_for_models():
    """A skill 'models' deve ser acionada sem mencionar '14b'."""
    skills = match_skills("Qual candidato SMART selecionar?")
    assert "models" in skills


def test_match_skills_benchmark_triggers_models():
    """'benchmark' é um gatilho legítimo para a skill 'models'."""
    skills = match_skills("Executar benchmark do candidato SMART")
    assert "models" in skills


def test_match_skills_registry_triggers_models():
    """'registry' e 'model registry' acionam a skill 'models'."""
    skills = match_skills("Consultar o model registry para listar candidatos")
    assert "models" in skills


def test_match_skills_git_action():
    """Ação de github ainda aciona skill correta."""
    skills_git = match_skills("Executar tarefa", next_action="Publicar release no github")
    assert "github" in skills_git


# =========================================================
# ACCEPTANCE GATE — regras SMART (não 14B)
# =========================================================

def test_acceptance_smart_candidate_rejects_single_candidate(tmp_path, monkeypatch):
    """Rejeita se houver menos de 2 candidatos SMART registrados."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Compatível com RTX 3070 8GB, offload parcial.",
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    accepted, reason = check_checklist_acceptance("Escolher modelo SMART candidato", completed=True)
    assert accepted is False
    assert "2 candidatos" in reason or "candidato" in reason


def test_acceptance_smart_candidate_rejects_without_justification(tmp_path, monkeypatch):
    """Rejeita se nenhum candidato SMART tiver justificativa técnica."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
            },
            "qwen2.5:14b": {
                "name": "Qwen 2.5 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
            }
        }
    }), encoding="utf-8")

    mem_file = tmp_path / "store.json"
    mem_file.write_text(json.dumps({"decisions": {}}), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)
    monkeypatch.setattr("core.harness.acceptance.MEMORY_STORE_PATH", mem_file)

    accepted, reason = check_checklist_acceptance("Escolher modelo SMART candidato", completed=True)
    assert accepted is False
    assert "justificativa" in reason


def test_acceptance_smart_candidate_rejects_hallucinated_model(tmp_path, monkeypatch):
    """Rejeita modelos alucinados (ex: llama3:14b que não existe oficialmente)."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "llama3:14b": {
                "name": "llama3:14b",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "teste",
            },
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Compatível com RTX 3070 8GB.",
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    accepted, reason = check_checklist_acceptance("Escolher modelo SMART candidato", completed=True)
    assert accepted is False
    assert "inválido" in reason or "não existe" in reason


def test_acceptance_smart_candidate_rejects_without_hardware_fit(tmp_path, monkeypatch):
    """Rejeita se candidatos não tiverem informações de hardware (vram_gb, size_gb)."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "justification": "Compatível com RTX 3070 8GB.",
                # sem size_gb e vram_gb
            },
            "qwen2.5:14b": {
                "name": "Qwen 2.5 14B",
                "role": "smart",
                "status": "candidate",
                "justification": "Candidato alternativo.",
                # sem size_gb e vram_gb
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    accepted, reason = check_checklist_acceptance("Escolher modelo SMART candidato", completed=True)
    assert accepted is False
    assert "hardware" in reason or "vram" in reason.lower()


def test_acceptance_smart_candidate_accepts_valid(tmp_path, monkeypatch):
    """Aceita quando há ≥2 candidatos SMART com justificativa e dados de hardware."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Compatível com RTX 3070 8GB VRAM usando Q4_K_M e offload parcial em RAM.",
            },
            "qwen2.5:14b": {
                "name": "Qwen 2.5 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Candidato alternativo com raciocínio geral.",
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    accepted, reason = check_checklist_acceptance("Escolher modelo SMART candidato", completed=True)
    assert accepted is True
    assert reason is None


def test_acceptance_legacy_item_text_still_validates_as_smart(tmp_path, monkeypatch):
    """
    Item legado 'Escolher modelo 14B candidato' ainda é validado como seleção SMART.
    O texto do item NÃO determina a regra arquitetural.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen2.5-coder:14b": {
                "name": "Qwen 2.5 Coder 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Compatível com RTX 3070 8GB VRAM usando Q4_K_M.",
            },
            "qwen2.5:14b": {
                "name": "Qwen 2.5 14B",
                "role": "smart",
                "status": "candidate",
                "size_gb": 9.0,
                "vram_gb": 8.0,
                "justification": "Candidato alternativo.",
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    # Texto legado "14b candidato" aciona a mesma regra SMART
    accepted, reason = check_checklist_acceptance("Escolher modelo 14B candidato", completed=True)
    assert accepted is True
    assert reason is None


# =========================================================
# MODEL REGISTRY TOOLS — lifecycle candidate/benchmark/adopted
# =========================================================

def test_tools_register_smart_candidate(tmp_path, monkeypatch):
    """Registrar candidato SMART — status inicial deve ser 'candidate'."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    res = register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Compatível com RTX 3070 8GB via offload em 16GB RAM",
    )
    assert res["success"] is True
    assert res["model"]["status"] == "candidate"
    assert res["model"]["role"] == "smart"


def test_tools_smart_role_not_dependent_on_14b(tmp_path, monkeypatch):
    """Um modelo pode ser SMART mesmo sem '14b' no nome."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    res = register_model_candidate(
        name="deepseek-coder-v2:16b",
        role="smart",
        backend="ollama",
        size_gb=10.5,
        vram_gb=9.0,
        description="Modelo especialista em código com 16B parâmetros",
        justification="Candidato SMART alternativo — tamanho 16B, não 14B.",
    )
    assert res["success"] is True
    assert res["model"]["role"] == "smart"
    # Papel SMART não depende de "14b" no nome
    assert "14b" not in res["model"]["name"]


def test_tools_candidate_not_equal_to_benchmark(tmp_path, monkeypatch):
    """'candidate' != 'selected_for_benchmark' — transição explícita necessária."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar como candidate
    register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Candidato SMART",
    )

    reg = get_model_registry(role="smart")
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "candidate"

    # Selecionar para benchmark
    bench = set_smart_candidate_for_benchmark("qwen2.5-coder:14b", rationale="Melhor candidato avaliado")
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    reg2 = get_model_registry(role="smart")
    assert reg2["models"]["qwen2.5-coder:14b"]["status"] == "selected_for_benchmark"
    # active_smart_model ainda não foi definido — não é "adopted"
    assert reg2["active_smart_model"] is None


def test_tools_benchmark_not_equal_to_adopted(tmp_path, monkeypatch):
    """'selected_for_benchmark' != 'adopted' — adoção requer set_active_smart_model."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Candidato SMART",
    )

    set_smart_candidate_for_benchmark("qwen2.5-coder:14b")

    # Antes de adotar: active_smart_model deve ser None
    reg = get_model_registry()
    assert reg["active_smart_model"] is None

    # Adotar formalmente
    act = set_active_smart_model("qwen2.5-coder:14b", justification="Aprovado no benchmark")
    assert act["success"] is True
    assert act["active_smart_model"] == "qwen2.5-coder:14b"

    reg2 = get_model_registry()
    assert reg2["active_smart_model"] == "qwen2.5-coder:14b"
    assert reg2["models"]["qwen2.5-coder:14b"]["status"] == "adopted"


def test_tools_model_registry_crud(tmp_path, monkeypatch):
    """Teste completo de CRUD: registrar, consultar, adotar via lifecycle correto."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # 1. Registrar candidato (qwen2.5-coder:14b como atributo factual do modelo)
    res = register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código e tool calling",
        justification="Excelente raciocínio e viável para RTX 3070 8GB com offload em 16GB RAM",
    )
    assert res["success"] is True

    # 2. Consultar registry
    reg = get_model_registry(role="smart")
    assert reg["success"] is True
    assert "qwen2.5-coder:14b" in reg["models"]

    # 3. Selecionar para benchmark (lifecycle obrigatório antes da adoção)
    bench = set_smart_candidate_for_benchmark("qwen2.5-coder:14b", rationale="Melhor candidato avaliado")
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    # 4. Adotar smart (após seleção formal para benchmark)
    act = set_active_smart_model("qwen2.5-coder:14b", justification="Eleito melhor candidato após benchmark")
    assert act["success"] is True
    assert act["active_smart_model"] == "qwen2.5-coder:14b"


# =========================================================
# FAST MODEL LIFECYCLE — candidate → selected_for_benchmark → adopted
# Infraestrutura equivalente à do SMART (Fases 7/8)
# =========================================================

def test_fast_can_be_candidate(tmp_path, monkeypatch):
    """FAST pode ser registrado como candidate — o mesmo status inicial do SMART."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    res = register_model_candidate(
        name="qwen3:4b",
        role="fast",
        backend="ollama",
        size_gb=2.5,
        vram_gb=3.0,
        description="Modelo FAST candidato leve",
        justification="Compatível com RTX 3070 8GB, menor latência para tarefas rotineiras.",
    )
    assert res["success"] is True
    assert res["model"]["status"] == "candidate"
    assert res["model"]["role"] == "fast"


def test_fast_can_be_selected_for_benchmark(tmp_path, monkeypatch):
    """FAST pode ser marcado como selected_for_benchmark — transição explícita necessária."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar candidato FAST
    register_model_candidate(
        name="qwen3:4b",
        role="fast",
        backend="ollama",
        size_gb=2.5,
        vram_gb=3.0,
        description="Candidato FAST",
        justification="Latência mínima para operações do harness.",
    )

    # Status inicial deve ser candidate
    reg = get_model_registry(role="fast")
    assert reg["models"]["qwen3:4b"]["status"] == "candidate"

    # Selecionar para benchmark
    bench = set_fast_candidate_for_benchmark("qwen3:4b", rationale="Melhor candidato FAST avaliado")
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    # Verificar no registry
    reg2 = get_model_registry(role="fast")
    assert reg2["models"]["qwen3:4b"]["status"] == "selected_for_benchmark"
    # active_fast_model NÃO muda automaticamente
    assert reg2["active_fast_model"] != "qwen3:4b"


def test_fast_can_be_adopted(tmp_path, monkeypatch):
    """FAST pode ser adotado formalmente após benchmark — requer set_active_fast_model()."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar e selecionar para benchmark
    register_model_candidate(
        name="qwen3:4b",
        role="fast",
        backend="ollama",
        size_gb=2.5,
        vram_gb=3.0,
        description="Candidato FAST",
        justification="Latência mínima.",
    )
    set_fast_candidate_for_benchmark("qwen3:4b")

    # Antes de adotar: active_fast_model ainda aponta para o bootstrap ou é None
    reg = get_model_registry()
    # active_fast_model não deve ser "qwen3:4b" ainda (nenhum bootstrap no tmp)
    assert reg["active_fast_model"] != "qwen3:4b"

    # Adotar formalmente
    act = set_active_fast_model("qwen3:4b", justification="Aprovado no benchmark FAST")
    assert act["success"] is True
    assert act["active_fast_model"] == "qwen3:4b"

    # Verificar adoção
    reg2 = get_model_registry()
    assert reg2["active_fast_model"] == "qwen3:4b"
    assert reg2["models"]["qwen3:4b"]["status"] == "adopted"


def test_fast_benchmark_not_equal_to_adopted(tmp_path, monkeypatch):
    """'selected_for_benchmark' != 'adopted' para FAST — adoção requer set_active_fast_model()."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    register_model_candidate(
        name="llama3.2:3b",
        role="fast",
        backend="ollama",
        size_gb=2.0,
        vram_gb=2.5,
        description="Candidato FAST alternativo",
        justification="Excelente throughput para tarefas simples.",
    )

    set_fast_candidate_for_benchmark("llama3.2:3b")

    # selected_for_benchmark não adota automaticamente
    reg = get_model_registry()
    assert reg["models"]["llama3.2:3b"]["status"] == "selected_for_benchmark"
    assert reg["active_fast_model"] != "llama3.2:3b"

    # Adoção formal
    set_active_fast_model("llama3.2:3b", justification="Melhor latência no benchmark")
    reg2 = get_model_registry()
    assert reg2["models"]["llama3.2:3b"]["status"] == "adopted"
    assert reg2["active_fast_model"] == "llama3.2:3b"


def test_fast_candidate_for_benchmark_requires_existing_model(tmp_path, monkeypatch):
    """set_fast_candidate_for_benchmark() falha se o modelo não foi registrado antes."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    res = set_fast_candidate_for_benchmark("modelo_fantasma:8b")
    assert res["success"] is False
    assert "não encontrado" in res["error"]


def test_qwen3_8b_not_automatically_adopted(monkeypatch):
    """qwen3:8b não é automaticamente adopted — status deve permanecer 'installed'."""
    from tools.models import get_model_registry
    reg = get_model_registry(role="fast")
    assert "qwen3:8b" in reg["models"]
    # qwen3:8b é bootstrap sem lifecycle formal: status deve ser "installed", não "adopted"
    assert reg["models"]["qwen3:8b"]["status"] == "installed"
    assert reg["models"]["qwen3:8b"]["status"] != "adopted"


def test_qwen3_8b_continues_installed():
    """qwen3:8b continua instalado e acessível — não foi removido, reinstalado ou alterado."""
    from tools.models import get_model_registry
    reg = get_model_registry()
    assert "qwen3:8b" in reg["models"]
    assert reg["models"]["qwen3:8b"]["role"] == "fast"
    assert reg["models"]["qwen3:8b"]["status"] == "installed"
    # active_fast_model ainda aponta para qwen3:8b (bootstrap)
    assert reg["active_fast_model"] == "qwen3:8b"


def test_smart_lifecycle_still_works(tmp_path, monkeypatch):
    """SMART lifecycle continua funcionando após adição do FAST lifecycle."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar candidato SMART
    res = register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Compatível com RTX 3070 8GB via offload em 16GB RAM.",
    )
    assert res["success"] is True
    assert res["model"]["role"] == "smart"
    assert res["model"]["status"] == "candidate"

    # Selecionar para benchmark
    bench = set_smart_candidate_for_benchmark("qwen2.5-coder:14b")
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    # Adotar
    act = set_active_smart_model("qwen2.5-coder:14b", justification="Aprovado no benchmark SMART")
    assert act["success"] is True
    assert act["active_smart_model"] == "qwen2.5-coder:14b"

    reg = get_model_registry()
    assert reg["active_smart_model"] == "qwen2.5-coder:14b"
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "adopted"


def test_fast_and_smart_are_roles_not_sizes(tmp_path, monkeypatch):
    """
    FAST e SMART são papéis arquiteturais — não dependem do tamanho do modelo.
    Um modelo com '3b' pode ser FAST; um com '32b' pode ser SMART.
    """
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Modelo pequeno como FAST
    fast_res = register_model_candidate(
        name="phi3:3.8b",
        role="fast",
        backend="ollama",
        size_gb=2.3,
        vram_gb=3.0,
        description="Modelo leve para operações rápidas",
        justification="Menor latência, ideal para bootstrap e tarefas rotineiras.",
    )
    assert fast_res["model"]["role"] == "fast"

    # Modelo grande como SMART
    smart_res = register_model_candidate(
        name="qwen2.5:32b",
        role="smart",
        backend="ollama",
        size_gb=20.0,
        vram_gb=8.0,
        description="Modelo especialista de alto raciocínio",
        justification="Raciocínio avançado com offload em RAM. Candidato SMART.",
    )
    assert smart_res["model"]["role"] == "smart"

    # Papéis são independentes do tamanho
    reg = get_model_registry()
    assert reg["models"]["phi3:3.8b"]["role"] == "fast"
    assert reg["models"]["qwen2.5:32b"]["role"] == "smart"


# =========================================================
# LIFECYCLE GUARD — set_active_smart_model rejeita candidate
# Cobre as brechas descobertas no segundo teste de autonomia
# =========================================================

def test_lifecycle_guard_rejects_candidate_direct_adoption(tmp_path, monkeypatch):
    """candidate → set_active_smart_model() deve ser REJEITADO (violação de lifecycle)."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar como candidate (status inicial)
    register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Candidato SMART para benchmark",
    )

    # Verificar que está como candidate
    reg = get_model_registry(role="smart")
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "candidate"

    # Tentar adotar diretamente — deve ser REJEITADO
    result = set_active_smart_model("qwen2.5-coder:14b", justification="Tentativa inválida")
    assert result["success"] is False
    assert "candidate" in result["error"]
    assert "selected_for_benchmark" in result["error"]

    # Registry NÃO deve ter sido alterado
    reg_after = get_model_registry()
    assert reg_after["active_smart_model"] is None
    assert reg_after["models"]["qwen2.5-coder:14b"]["status"] == "candidate"


def test_lifecycle_guard_rejects_unregistered_model(tmp_path, monkeypatch):
    """Modelo não registrado no registry também é rejeitado por set_active_smart_model."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Tentar adotar modelo que nem está no registry
    result = set_active_smart_model("modelo-fantasma:7b", justification="Não deveria funcionar")
    assert result["success"] is False
    assert "não encontrado" in result["error"].lower() or "registry" in result["error"].lower()

    # active_smart_model continua None
    reg = get_model_registry()
    assert reg["active_smart_model"] is None


def test_lifecycle_guard_allows_adoption_after_benchmark_selection(tmp_path, monkeypatch):
    """selected_for_benchmark → set_active_smart_model() deve ser ACEITO."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Candidato SMART para benchmark",
    )

    # Transição correta: candidate → selected_for_benchmark
    bench = set_smart_candidate_for_benchmark("qwen2.5-coder:14b", rationale="Melhor candidato avaliado")
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    # Agora a adoção deve ser ACEITA
    result = set_active_smart_model("qwen2.5-coder:14b", justification="Aprovado no benchmark")
    assert result["success"] is True
    assert result["active_smart_model"] == "qwen2.5-coder:14b"

    reg = get_model_registry()
    assert reg["active_smart_model"] == "qwen2.5-coder:14b"
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "adopted"


def test_lifecycle_guard_does_not_alter_registry_on_failure(tmp_path, monkeypatch):
    """Nenhuma tentativa inválida altera active_smart_model nem o status do modelo."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    # Registrar dois candidatos
    for name in ["qwen2.5-coder:14b", "qwen2.5:14b"]:
        register_model_candidate(
            name=name,
            role="smart",
            backend="ollama",
            size_gb=9.0,
            vram_gb=8.0,
            description="Candidato SMART",
            justification="Avaliado para benchmark",
        )

    # Tentar adotar candidate diretamente — duas vezes
    res1 = set_active_smart_model("qwen2.5-coder:14b", justification="Tentativa 1")
    res2 = set_active_smart_model("qwen2.5:14b", justification="Tentativa 2")

    assert res1["success"] is False
    assert res2["success"] is False

    # Registry deve estar inalterado
    reg = get_model_registry()
    assert reg["active_smart_model"] is None
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "candidate"
    assert reg["models"]["qwen2.5:14b"]["status"] == "candidate"


# =========================================================
# ACCEPTANCE — BAIXAR MODELO usa candidato selected_for_benchmark
# Cobre o risco residual identificado no segundo teste de autonomia
# =========================================================

def test_baixar_modelo_rejected_when_no_selected_for_benchmark(tmp_path, monkeypatch):
    """
    qwen3:8b instalado + candidato SMART apenas como 'candidate' = REJEITADO.
    A presença de qualquer modelo instalado não satisfaz 'Baixar modelo'.
    """
    reg_file = tmp_path / "registry.json"
    reg_data = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen3:8b": {
                "name": "Qwen3 8B", "role": "fast", "backend": "ollama",
                "size_gb": 5.2, "vram_gb": 5.5, "context_window": 32768,
                "status": "installed", "description": "FAST bootstrap",
            },
            "qwen2.5-coder:14b": {
                "name": "qwen2.5-coder:14b", "role": "smart", "backend": "ollama",
                "size_gb": 9.0, "vram_gb": 8.0, "context_window": 32768,
                "status": "candidate",  # ← apenas candidate, não selected_for_benchmark
                "description": "Candidato SMART",
                "justification": "Avaliado para benchmark",
            },
        },
    }
    reg_file.write_text(json.dumps(reg_data, indent=2), encoding="utf-8")
    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    # ollama list retorna qwen3:8b instalado — mas não deve satisfazer a condição
    import unittest.mock as mock
    fake_ollama = mock.MagicMock()
    fake_ollama.stdout = "NAME\nqwen3:8b   abc123   5.2 GB   2 weeks ago\n"
    fake_ollama.returncode = 0

    with mock.patch("subprocess.run", return_value=fake_ollama):
        accepted, reason = check_checklist_acceptance("Baixar modelo", completed=True)

    assert accepted is False
    assert reason is not None
    assert "selected_for_benchmark" in reason


def test_baixar_modelo_rejected_when_smart_not_installed(tmp_path, monkeypatch):
    """
    Candidato SMART em selected_for_benchmark mas NÃO instalado = REJEITADO.
    O modelo selecionado precisa estar realmente no Ollama.
    """
    reg_file = tmp_path / "registry.json"
    reg_data = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen3:8b": {
                "name": "Qwen3 8B", "role": "fast", "backend": "ollama",
                "size_gb": 5.2, "vram_gb": 5.5, "context_window": 32768,
                "status": "installed", "description": "FAST bootstrap",
            },
            "qwen2.5-coder:14b": {
                "name": "qwen2.5-coder:14b", "role": "smart", "backend": "ollama",
                "size_gb": 9.0, "vram_gb": 8.0, "context_window": 32768,
                "status": "selected_for_benchmark",  # ← selecionado mas não instalado
                "description": "Candidato SMART",
                "justification": "Avaliado para benchmark",
            },
        },
    }
    reg_file.write_text(json.dumps(reg_data, indent=2), encoding="utf-8")
    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    # ollama list retorna apenas qwen3:8b — qwen2.5-coder:14b NÃO está instalado
    import unittest.mock as mock
    fake_ollama = mock.MagicMock()
    fake_ollama.stdout = "NAME\nqwen3:8b   abc123   5.2 GB   2 weeks ago\n"
    fake_ollama.returncode = 0

    with mock.patch("subprocess.run", return_value=fake_ollama):
        accepted, reason = check_checklist_acceptance("Baixar modelo", completed=True)

    assert accepted is False
    assert reason is not None
    assert "qwen2.5-coder:14b" in reason


def test_baixar_modelo_accepted_when_selected_smart_is_installed(tmp_path, monkeypatch):
    """
    Candidato SMART em selected_for_benchmark E instalado no Ollama = ACEITO.
    """
    reg_file = tmp_path / "registry.json"
    reg_data = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen3:8b": {
                "name": "Qwen3 8B", "role": "fast", "backend": "ollama",
                "size_gb": 5.2, "vram_gb": 5.5, "context_window": 32768,
                "status": "installed", "description": "FAST bootstrap",
            },
            "qwen2.5-coder:14b": {
                "name": "qwen2.5-coder:14b", "role": "smart", "backend": "ollama",
                "size_gb": 9.0, "vram_gb": 8.0, "context_window": 32768,
                "status": "selected_for_benchmark",
                "description": "Candidato SMART",
                "justification": "Avaliado para benchmark",
            },
        },
    }
    reg_file.write_text(json.dumps(reg_data, indent=2), encoding="utf-8")
    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    # ollama list agora mostra qwen2.5-coder:14b instalado
    import unittest.mock as mock
    fake_ollama = mock.MagicMock()
    fake_ollama.stdout = (
        "NAME\n"
        "qwen3:8b            abc123   5.2 GB   2 weeks ago\n"
        "qwen2.5-coder:14b   def456   9.0 GB   1 hour ago\n"
    )
    fake_ollama.returncode = 0

    with mock.patch("subprocess.run", return_value=fake_ollama):
        accepted, reason = check_checklist_acceptance("Baixar modelo", completed=True)

    assert accepted is True
    assert reason is None


def test_baixar_modelo_rejected_when_no_smart_selected_at_all(tmp_path, monkeypatch):
    """
    Sem nenhum candidato SMART no registry = REJEITADO.
    """
    reg_file = tmp_path / "registry.json"
    reg_data = {
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {
            "qwen3:8b": {
                "name": "Qwen3 8B", "role": "fast", "backend": "ollama",
                "size_gb": 5.2, "vram_gb": 5.5, "context_window": 32768,
                "status": "installed", "description": "FAST bootstrap",
            },
        },
    }
    reg_file.write_text(json.dumps(reg_data, indent=2), encoding="utf-8")
    monkeypatch.setattr("core.harness.acceptance.REGISTRY_PATH", reg_file)

    import unittest.mock as mock
    fake_ollama = mock.MagicMock()
    fake_ollama.stdout = "NAME\nqwen3:8b   abc123   5.2 GB   2 weeks ago\n"

    with mock.patch("subprocess.run", return_value=fake_ollama):
        accepted, reason = check_checklist_acceptance("Baixar modelo", completed=True)

    assert accepted is False
    assert "selected_for_benchmark" in reason


# =========================================================
# MANAGER — set_smart_candidate_for_benchmark via tool registry
# Testes adicionados após o teste de autonomia revelar que a
# ferramenta existia em models.py mas não estava registrada
# no manager.py (correção 1).
# =========================================================

def test_manager_has_set_smart_candidate_for_benchmark():
    """A ferramenta set_smart_candidate_for_benchmark deve aparecer no TOOL_REGISTRY."""
    from tools.manager import list_tools
    assert "set_smart_candidate_for_benchmark" in list_tools()


def test_manager_resolves_set_smart_candidate_by_name():
    """execute_tool deve reconhecer set_smart_candidate_for_benchmark como ferramenta válida."""
    from tools.manager import execute_tool
    # Tentar com nome de modelo inexistente — deve retornar erro da implementação,
    # não "Ferramenta desconhecida", provando que o manager a resolveu corretamente.
    result = execute_tool(
        "set_smart_candidate_for_benchmark",
        {"model_name": "modelo_que_nao_existe:99b"},
    )
    assert result.get("tool_error") is not True or "desconhecida" not in result.get("error", "")
    # A implementação devolve success=False com erro de "não encontrado" — não "desconhecida"
    assert result["success"] is False
    assert "não encontrado" in result["error"]


def test_manager_set_smart_candidate_valid_call(tmp_path, monkeypatch):
    """Chamada válida via manager executa a transição candidate → selected_for_benchmark."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    from tools.manager import execute_tool

    # Registrar candidato diretamente para ter o modelo no registry isolado
    register_model_candidate(
        name="qwen2.5-coder:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Especialista em código",
        justification="Candidato SMART para benchmark via manager",
    )

    # Chamar via manager (mesmo caminho que o agente usa)
    result = execute_tool(
        "set_smart_candidate_for_benchmark",
        {"model_name": "qwen2.5-coder:14b", "rationale": "Melhor candidato técnico"},
    )

    assert result["success"] is True
    assert result["status"] == "selected_for_benchmark"
    assert result["model"] == "qwen2.5-coder:14b"

    # Confirmar que o registry reflete a mudança
    reg = get_model_registry(role="smart")
    assert reg["models"]["qwen2.5-coder:14b"]["status"] == "selected_for_benchmark"
    # active_smart_model ainda não foi alterado
    assert reg["active_smart_model"] is None


def test_manager_set_smart_candidate_invalid_call_missing_arg():
    """Chamada sem model_name (argumento obrigatório) deve ser rejeitada pelo manager."""
    from tools.manager import execute_tool
    result = execute_tool(
        "set_smart_candidate_for_benchmark",
        {},  # sem model_name
    )
    assert result["success"] is False
    assert result.get("tool_error") is True
    assert "model_name" in result["error"]


def test_lifecycle_guard_still_protected_after_manager_registration(tmp_path, monkeypatch):
    """
    Garantia de que registrar set_smart_candidate_for_benchmark no manager
    não afetou o lifecycle guard de set_active_smart_model.

    candidate → set_active_smart_model() ainda deve ser REJEITADO.
    candidate → set_smart_candidate_for_benchmark() → set_active_smart_model() = ACEITO.
    """
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr("tools.models.REGISTRY_PATH", reg_file)

    from tools.manager import execute_tool

    register_model_candidate(
        name="qwen2.5:14b",
        role="smart",
        backend="ollama",
        size_gb=9.0,
        vram_gb=8.0,
        description="Candidato raciocínio geral",
        justification="Candidato SMART alternativo",
    )

    # Tentativa direta de adoção — lifecycle guard deve rejeitar
    direct = execute_tool("set_active_smart_model", {"model_name": "qwen2.5:14b"})
    assert direct["success"] is False
    assert "selected_for_benchmark" in direct["error"]

    # Lifecycle correto via manager
    bench = execute_tool(
        "set_smart_candidate_for_benchmark",
        {"model_name": "qwen2.5:14b", "rationale": "Aprovado para benchmark"},
    )
    assert bench["success"] is True
    assert bench["status"] == "selected_for_benchmark"

    adopt = execute_tool(
        "set_active_smart_model",
        {"model_name": "qwen2.5:14b", "justification": "Aprovado no benchmark"},
    )
    assert adopt["success"] is True
    assert adopt["active_smart_model"] == "qwen2.5:14b"

    # Registry final correto
    reg = get_model_registry()
    assert reg["active_smart_model"] == "qwen2.5:14b"
    assert reg["models"]["qwen2.5:14b"]["status"] == "adopted"
