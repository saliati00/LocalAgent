import pytest
from pathlib import Path

from core.harness.project_progress import (
    extract_project_progress,
    update_project_checklist,
    format_project_summary,
)


SAMPLE_SPEC = """# Projeto Teste

## FASE 0 — SETUP

* [x] Item 1 concluido
* [x] Item 2 concluido

## FASE 1 — OPERACAO

* [x] Ferramenta A
* [ ] Ferramenta B
* [ ] Ferramenta C

## FASE 2 — ESCALADA

* [ ] Modelo SMART
"""


def test_extract_project_progress(tmp_path):
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

    progress = extract_project_progress(str(spec_file))
    assert progress["success"] is True
    assert progress["current_phase"] == "FASE 1 — OPERACAO"
    assert progress["next_action"] == "Ferramenta B"
    assert progress["pending_count"] == 3


def test_update_project_checklist(tmp_path):
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

    # Marca Ferramenta B como concluida
    result = update_project_checklist(str(spec_file), "Ferramenta B", completed=True)
    assert result["success"] is True

    # Re-extrai progresso
    progress = extract_project_progress(str(spec_file))
    assert progress["success"] is True
    assert progress["next_action"] == "Ferramenta C"
    assert progress["pending_count"] == 2

    # Verifica conteudo no disco
    content = spec_file.read_text(encoding="utf-8")
    assert "* [x] Ferramenta B" in content


def test_update_project_checklist_already_in_state(tmp_path):
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

    # Item 1 já está concluído [x]
    res1 = update_project_checklist(str(spec_file), "Item 1 concluido", completed=True)
    assert res1["success"] is True
    assert res1["already_in_state"] is True

    # Ferramenta B está pendente [ ]
    res2 = update_project_checklist(str(spec_file), "Ferramenta B", completed=False)
    assert res2["success"] is True
    assert res2["already_in_state"] is True

    # Ferramenta B marcada como [x] (mudança real)
    res3 = update_project_checklist(str(spec_file), "Ferramenta B", completed=True)
    assert res3["success"] is True
    assert res3["already_in_state"] is False


def test_format_project_summary(tmp_path):
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

    progress = extract_project_progress(str(spec_file))
    summary = format_project_summary(progress)

    assert "FASE 1 — OPERACAO" in summary
    assert "Ferramenta B" in summary
    assert "Ferramenta A" in summary
