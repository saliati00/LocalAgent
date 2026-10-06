import pytest

import agent
import core.prompts as prompts


@pytest.fixture
def prompt_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    (tmp_path / "ola.md").write_text("  Faça isto.\n", encoding="utf-8")
    (tmp_path / "vazio.md").write_text("   \n", encoding="utf-8")
    return tmp_path


def test_load_prompt_returns_trimmed_text(prompt_dir):
    assert prompts.load_prompt("ola") == (True, "Faça isto.")


def test_list_prompts(prompt_dir):
    assert prompts.list_prompts() == ["ola", "vazio"]


@pytest.mark.parametrize("name", ["", "../specs/projeto", "a b", "nao-existe", "vazio"])
def test_load_prompt_rejects_bad_empty_or_missing(prompt_dir, name):
    ok, message = prompts.load_prompt(name)

    assert ok is False
    assert message


def test_resolve_prompt_expands_at_names_and_passes_plain_text(prompt_dir):
    assert agent.resolve_prompt("@ola") == "Faça isto."
    assert agent.resolve_prompt("  verifique o git  ") == "verifique o git"
    assert agent.resolve_prompt("@nao-existe") is None


def test_saved_development_prompt_triggers_the_development_flow():
    ok, text = prompts.load_prompt("iniciar-desenvolvimento")

    assert ok is True
    lowered = text.lower()

    # Palavras que o agent.py usa para reconhecer uma tarefa de desenvolvimento.
    assert "continue" in lowered and "specs/projeto.md" in lowered
    assert len(text) < 1500, "prompt longo demais consome o contexto"
