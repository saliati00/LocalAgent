from core.harness.acceptance import check_checklist_acceptance
from core.harness.project_progress import extract_project_progress
from core.paths import PROJECT_SPEC_PATH


def test_agent_cannot_complete_human_items():
    accepted, reason = check_checklist_acceptance("[humano] Medir no PC alvo o consumo real do prompt", True)

    assert accepted is False
    assert "usuário" in reason


def test_unmarking_a_human_item_is_still_allowed():
    accepted, _ = check_checklist_acceptance("[humano] Medir no PC alvo o consumo real do prompt", False)
    assert accepted is True


def test_regular_items_are_not_affected_by_the_human_rule():
    accepted, _ = check_checklist_acceptance("Qualquer item comum do checklist", True)
    assert accepted is True


def test_the_next_action_is_never_a_human_item_while_the_agent_has_something_to_do():
    progress = extract_project_progress(str(PROJECT_SPEC_PATH))
    doable = [entry for entry in progress["pending"] if entry not in progress["human_pending"]]

    assert progress["human_pending"], "os itens [humano] da FASE 11 continuam pendentes"
    assert doable, "ainda há itens que o agente pode fazer"
    assert not progress["next_action"].lower().startswith("[humano]")
    assert progress["next_action"] == doable[0]["item"]


def test_human_items_are_skipped_even_when_they_come_first(tmp_path):
    spec = tmp_path / "projeto.md"
    spec.write_text(
        "## FASE 1 — TESTE\n* [ ] [humano] Medir no PC\n* [ ] Escrever o módulo\n\n## FASE 2 — OUTRA\n* [ ] Outra coisa\n",
        encoding="utf-8",
    )

    progress = extract_project_progress(str(spec))

    assert progress["next_action"] == "Escrever o módulo" and progress["current_phase"].startswith("FASE 1")
    assert [entry["item"] for entry in progress["human_pending"]] == ["[humano] Medir no PC"]


def test_when_only_human_items_remain_the_first_of_them_is_reported(tmp_path):
    spec = tmp_path / "projeto.md"
    spec.write_text("## FASE 1 — TESTE\n* [ ] [humano] Medir no PC\n* [x] Feito\n", encoding="utf-8")

    progress = extract_project_progress(str(spec))

    assert progress["next_action"] == "[humano] Medir no PC"
