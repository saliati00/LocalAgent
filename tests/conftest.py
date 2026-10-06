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
