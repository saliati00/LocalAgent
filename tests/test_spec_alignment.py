"""A especificação, o registro de modelos e a memória refletem o rumo atual do projeto."""

import json

from core.harness.project_progress import extract_project_progress
from core.memory.store import MemoryStore
from core.paths import MEMORY_STORE_PATH, PROJECT_ROOT, PROJECT_SPEC_PATH, REGISTRY_PATH

HISTORY = PROJECT_ROOT / "specs" / "historico.md"


def spec():
    return PROJECT_SPEC_PATH.read_text(encoding="utf-8")


def test_the_spec_has_a_current_direction_chapter_that_points_to_the_history():
    text = spec()

    assert "# 39. RUMO ATUAL" in text and "specs/historico.md" in text
    assert "Open WebUI" in text and "FASE 10" in text


def test_the_round_by_round_diary_lives_in_the_history_file():
    history = HISTORY.read_text(encoding="utf-8")

    for chapter in ("# 39. EVIDÊNCIAS DOS LOGS", "# 48. PRIMEIRA RODADA REAL", "# 60. CORREÇÕES"):
        assert chapter in history and chapter not in spec()


def test_old_chapter_titles_were_updated():
    text = spec()

    assert "# 5. PAPEL DO FAST" in text and "# 5. PAPEL DO 8B" not in text
    assert "# 27. FERRAMENTAS EXTERNAS DE DESENVOLVIMENTO" in text
    assert "## FASE 1 — FAST OPERADOR" in text
    assert "Ollama 0.35.1" not in text


def test_the_checklist_still_parses_and_the_web_interface_choice_is_ticked():
    progress = extract_project_progress(str(PROJECT_SPEC_PATH))

    assert progress["success"] and progress["pending_count"] > 0
    assert "* [x] Escolher interface/harness web" in spec()


def test_the_registry_lists_the_current_candidates_with_justification():
    models = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["models"]

    for name, role in (("qwen3.5:9b", "fast"), ("qwen3.5:4b", "fast"), ("gemma4:12b", "smart"), ("gpt-oss:20b", "smart")):
        assert models[name]["role"] == role and models[name]["status"] == "candidate" and models[name]["justification"], name

    assert "qwen2.5:14b" not in models and "qwen2.5-coder:14b" not in models


def test_the_agent_memory_no_longer_carries_fedora_paths_or_old_model_decisions():
    context = MemoryStore(MEMORY_STORE_PATH).format_context()

    for stale in ("/usr/bin", "/home/", "qwen2.5", "llama3.2", "Fedora 44 KDE (Linux"):
        assert stale not in context, stale

    assert "Windows" in context and "RTX 3070" in context
