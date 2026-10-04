import pytest
from core.skills.loader import (
    list_skills,
    load_skill,
    match_skills,
    format_skills_context,
)


def test_list_skills():
    skills = list_skills()
    assert "environment" in skills
    assert "development" in skills
    assert "linux" in skills
    assert "github" in skills
    assert "models" in skills


def test_load_skill():
    res = load_skill("development")
    assert res["success"] is True
    assert "Desenvolvimento Autônomo" in res["content"]


def test_match_skills():
    # Prompt de desenvolvimento
    matched = match_skills("Continue o desenvolvimento do projeto conforme specs/projeto.md")
    assert "development" in matched

    # Prompt de github
    matched_git = match_skills("Pesquise a ultima release do Ollama no github")
    assert "github" in matched_git

    # Prompt de modelo — acionado por conceitos SMART, não por "14b"
    matched_mod = match_skills("Qual candidato SMART podemos selecionar para benchmark?")
    assert "models" in matched_mod

    # Prompt com "smart" explícito
    matched_smart = match_skills("Escolher modelo smart para o sistema")
    assert "models" in matched_smart

    # Prompt com "registry"
    matched_reg = match_skills("Consultar o model registry de candidatos")
    assert "models" in matched_reg


def test_format_skills_context():
    res = load_skill("development")
    text = format_skills_context([res])
    assert "SKILL: DEVELOPMENT" in text
    assert "FIM DA SKILL: DEVELOPMENT" in text
