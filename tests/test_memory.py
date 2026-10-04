import pytest
from core.memory.store import MemoryStore


def test_memory_store_crud(tmp_path):
    mem_file = tmp_path / "test_store.json"
    store = MemoryStore(file_path=mem_file)

    # Test initial state
    assert store.get_all()["environment"] == {}

    # Test set & get
    res = store.set("environment", "git", "/usr/bin/git", "Ferramenta Git oficial")
    assert res["success"] is True
    assert store.get("environment", "git") == "/usr/bin/git"

    # Test get_entry
    entry = store.get_entry("environment", "git")
    assert entry is not None
    assert entry["value"] == "/usr/bin/git"
    assert entry["description"] == "Ferramenta Git oficial"
    assert "updated_at" in entry

    # Test persistence across re-instantiation
    store2 = MemoryStore(file_path=mem_file)
    assert store2.get("environment", "git") == "/usr/bin/git"

    # Test delete
    assert store2.delete("environment", "git") is True
    assert store2.get("environment", "git") is None
    assert store2.delete("environment", "git") is False


def test_memory_store_format_context(tmp_path):
    mem_file = tmp_path / "test_store.json"
    store = MemoryStore(file_path=mem_file)

    store.set("environment", "cmake", "4.4.3", "Compilador cmake instalado no .venv")
    store.set("decisions", "harness", "Harness proprio adotado", "Controle total da execucao")

    ctx = store.format_context()
    assert "MEMÓRIA PERSISTENTE DO AGENTE" in ctx
    assert "cmake: 4.4.3" in ctx
    assert "Compilador cmake instalado no .venv" in ctx
    assert "Harness proprio adotado" in ctx


def test_memory_store_clear_category(tmp_path):
    mem_file = tmp_path / "test_store.json"
    store = MemoryStore(file_path=mem_file)

    store.set("notes", "tarefa_1", "em andamento")
    assert store.get("notes", "tarefa_1") == "em andamento"

    store.clear_category("notes")
    assert store.get("notes", "tarefa_1") is None
