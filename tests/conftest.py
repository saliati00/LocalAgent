import pytest

from core.memory.store import MemoryStore


@pytest.fixture(autouse=True)
def isolate_memory_store(tmp_path, monkeypatch):
    """
    Impede que os testes gravem no memory/store.json real do projeto.

    tools.models e tools.manager criam um MemoryStore global na importação;
    cada teste passa a usar um arquivo temporário.
    """
    import tools.manager
    import tools.models

    store = MemoryStore(str(tmp_path / "isolated_store.json"))
    monkeypatch.setattr(tools.models, "_memory_store", store)
    monkeypatch.setattr(tools.manager, "_memory_store", store)


@pytest.fixture(autouse=True)
def isolate_log_file(tmp_path, monkeypatch):
    """Os testes não escrevem no logs/agent.log real."""
    from core.harness import logger

    monkeypatch.setattr(logger, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(logger, "LOG_FILE", tmp_path / "logs" / "agent.log")


@pytest.fixture(autouse=True)
def no_interactive_model_confirmation(monkeypatch):
    """Os testes de registry chamam as tools sem terminal; os testes de confirmação ligam de volta."""
    import tools.manager

    monkeypatch.setattr(tools.manager, "CONFIRM_MODEL_GOVERNANCE", False)
