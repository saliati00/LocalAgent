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


def test_first_pending_item_of_phase_11_is_doable_by_the_agent():
    progress = extract_project_progress(str(PROJECT_SPEC_PATH))

    assert progress["current_phase"].startswith("FASE 11")
    assert not progress["next_action"].lower().startswith("[humano]")
