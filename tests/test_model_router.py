import json
import pytest
from core.router.model_router import ModelRouter


def test_model_router_default_uses_fast():
    """Por padrão, o router usa o modelo FAST registrado no registry.json."""
    router = ModelRouter()
    model = router.route_task("Liste os arquivos no diretorio")
    # O registry.json real possui active_fast_model = "qwen3:8b"
    assert model == "qwen3:8b"


def test_model_router_fast_model_from_registry(tmp_path):
    """get_fast_model() retorna o valor configurado no registry, não um hardcode."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_fast_model() == "qwen3:8b"


def test_model_router_fast_model_none_when_not_registered(tmp_path):
    """get_fast_model() retorna None quando nenhum FAST está definido no registry."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": None,
        "active_smart_model": None,
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_fast_model() is None


def test_model_router_fast_model_none_when_registry_missing(tmp_path):
    """Sem registry.json, get_fast_model() retorna None — sem hardcode de modelo."""
    reg_file = tmp_path / "nonexistent_registry.json"
    router = ModelRouter(registry_path=reg_file)
    # O router NÃO deve assumir nenhum modelo FAST por padrão
    assert router.get_fast_model() is None


def test_model_router_smart_model_is_none_when_not_adopted():
    """Se nenhum modelo SMART foi adotado, get_smart_model() retorna None."""
    router = ModelRouter()
    # O fallback padrão não é mais qwen2.5-coder:14b — é None
    smart = router.get_smart_model()
    # Sem registry, deve ser None (não um hardcode de 14B)
    assert smart is None


def test_model_router_no_14b_hardcode_in_fallback(tmp_path):
    """
    Verifica que o router NÃO usa qwen2.5-coder:14b como fallback arquitetural.
    O SMART é determinado pelo registry, não pelo tamanho do modelo.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": None,
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_smart_model() is None
    # Roteamento cai para FAST quando SMART não está disponível
    model = router.route_task("Refatorar toda a arquitetura com raciocínio especialista")
    assert model == "qwen3:8b"


def test_model_router_no_fast_hardcode_in_fallback(tmp_path):
    """
    O router NÃO assume qwen3:8b como FAST quando o registry não define active_fast_model.
    FAST e SMART são papéis resolvidos pelo registry — não por hardcode.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": None,
        "active_smart_model": None,
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)
    # Sem FAST definido, deve retornar None — não "qwen3:8b" hardcoded
    assert router.get_fast_model() is None
    result = router.route_task("Execute uma tarefa simples")
    assert result is None


def test_model_router_fast_any_model_name(tmp_path):
    """O papel FAST pode ser atribuído a qualquer modelo — não é exclusivo do qwen3:8b."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "llama3.2:3b",
        "active_smart_model": None,
        "models": {},
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_fast_model() == "llama3.2:3b"
    model = router.route_task("Liste os arquivos")
    assert model == "llama3.2:3b"
    # O papel FAST não exige "qwen3" no nome
    assert "qwen3" not in model


def test_model_router_routes_to_smart_when_adopted_and_installed(tmp_path):
    """
    Router usa SMART quando: (1) adotado no registry, (2) status=installed,
    (3) prompt pede explicitamente smart/especialista.
    O modelo SMART pode ter qualquer tamanho — não precisa ser 14B.
    """
    reg_file = tmp_path / "registry.json"
    # Usar um modelo hipotético 20B para provar que não é dependência de 14B
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "qwen2.5-coder:20b",
        "models": {
            "qwen2.5-coder:20b": {
                "role": "smart",
                "status": "installed",
            }
        },
    }))
    router = ModelRouter(registry_path=reg_file)
    model = router.route_task("Use o modelo especialista para refatorar o código")
    assert model == "qwen2.5-coder:20b"
    # Confirma que não é 14B por padrão
    assert "14b" not in model


def test_model_router_smart_factual_14b_candidate(tmp_path):
    """
    14B pode aparecer como atributo factual de um candidato SMART adotado.
    Quando adotado e instalado, o router deve usá-lo quando pedido.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "qwen2.5-coder:14b",
        "models": {
            "qwen2.5-coder:14b": {
                "role": "smart",
                "status": "installed",
            }
        },
    }))
    router = ModelRouter(registry_path=reg_file)
    model = router.route_task("Analise com o modelo especialista smart")
    assert model == "qwen2.5-coder:14b"


def test_model_router_smart_not_routed_when_not_installed(tmp_path):
    """SMART não é usado quando status != 'installed', mesmo que adotado."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "qwen3:8b",
        "active_smart_model": "qwen2.5-coder:14b",
        "models": {
            "qwen2.5-coder:14b": {
                "role": "smart",
                "status": "candidate",  # não instalado
            }
        },
    }))
    router = ModelRouter(registry_path=reg_file)
    model = router.route_task("Use o modelo especialista para analisar")
    # Não está instalado → cai para FAST
    assert model == "qwen3:8b"


def test_model_router_escalation_no_errors():
    router = ModelRouter()
    escalate, reason = router.should_escalate(consecutive_errors=0, iteration=5, tool_failures=0)
    assert escalate is False
    assert reason == ""


def test_model_router_escalation_on_consecutive_errors():
    router = ModelRouter()
    escalate, reason = router.should_escalate(consecutive_errors=3, iteration=8, tool_failures=3)
    assert escalate is True
    assert "erros consecutivos" in reason


def test_model_router_escalation_on_many_iterations():
    router = ModelRouter()
    escalate, reason = router.should_escalate(consecutive_errors=1, iteration=20, tool_failures=6)
    assert escalate is True
    assert "iterações" in reason or "falhas" in reason


def test_model_router_register_model(tmp_path):
    """Registrar modelo com papel SMART independe de tamanho."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({"active_fast_model": "qwen3:8b", "active_smart_model": None, "models": {}}))
    router = ModelRouter(registry_path=reg_file)
    router.register_model(
        name="mistral-nemo:12b",
        role="smart",
        backend="ollama",
        status="candidate",
    )
    models = router.list_models()
    assert "mistral-nemo:12b" in models
    assert models["mistral-nemo:12b"]["role"] == "smart"
    # Papel SMART pode ser atribuído a qualquer modelo, independente de tamanho


def test_model_router_register_fast_candidate(tmp_path):
    """Registrar modelo FAST candidato — papel FAST não é exclusivo do qwen3:8b."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({"active_fast_model": "qwen3:8b", "active_smart_model": None, "models": {}}))
    router = ModelRouter(registry_path=reg_file)
    router.register_model(
        name="qwen3:4b",
        role="fast",
        backend="ollama",
        status="candidate",
    )
    models = router.list_models()
    assert "qwen3:4b" in models
    assert models["qwen3:4b"]["role"] == "fast"
    assert models["qwen3:4b"]["status"] == "candidate"


def test_model_router_qwen3_8b_remains_installed():
    """qwen3:8b continua registrado no registry como fast/installed (não adopted via lifecycle)."""
    router = ModelRouter()
    models = router.list_models()
    assert "qwen3:8b" in models
    assert models["qwen3:8b"]["role"] == "fast"
    assert models["qwen3:8b"]["status"] == "installed"
    # qwen3:8b não possui status "adopted" — nunca passou pelo lifecycle formal
    assert models["qwen3:8b"]["status"] != "adopted"


def test_model_router_fast_and_smart_are_roles_not_sizes(tmp_path):
    """
    FAST e SMART são papéis arquiteturais, não dependem do tamanho do modelo.
    Um modelo com '3b' pode ser FAST; um com '32b' pode ser SMART.
    """
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "active_fast_model": "phi3:3.8b",
        "active_smart_model": "qwen2.5:32b",
        "models": {
            "phi3:3.8b": {"role": "fast", "status": "installed"},
            "qwen2.5:32b": {"role": "smart", "status": "installed"},
        },
    }))
    router = ModelRouter(registry_path=reg_file)
    assert router.get_fast_model() == "phi3:3.8b"
    assert router.get_smart_model() == "qwen2.5:32b"
    # Roteamento funciona por papel, não por tamanho
    fast_result = router.route_task("Lista arquivos")
    smart_result = router.route_task("Use o especialista smart para analisar")
    assert fast_result == "phi3:3.8b"
    assert smart_result == "qwen2.5:32b"
