"""As tarefas realistas da bateria: o verificador reprova o estado inicial, aprova uma solução correta e não se deixa enganar."""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bateria  # noqa: E402
import tarefas_reais as real  # noqa: E402

TASKS = {task["id"]: task for task in real.TASKS}


def build(tmp_path, task, with_solution=False):
    folder = tmp_path / task["id"]
    files = {**task["files"], **(task["solution"] if with_solution else {})}

    for name, content in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return folder


def test_there_are_ten_realistic_tasks_with_unique_ids_and_natural_prompts():
    ids = [task["id"] for task in real.TASKS]

    assert len(ids) == len(set(ids)) == 10

    for task in real.TASKS:
        assert "{dir}" in task["prompt"] and task["files"] and callable(task["check"]) and task["solution"]
        assert "write_file" not in task["prompt"], "o pedido deve soar como um usuário, não como instrução de ferramenta"


@pytest.mark.parametrize("task_id", list(TASKS))
def test_initial_state_is_rejected(tmp_path, task_id):
    task = TASKS[task_id]
    folder = build(tmp_path, task)

    ok, detail = task["check"](folder)

    assert ok is False, f"{task_id} aprovou o estado inicial: {detail}"


@pytest.mark.parametrize("task_id", list(TASKS))
def test_a_correct_solution_is_accepted(tmp_path, task_id):
    task = TASKS[task_id]
    folder = build(tmp_path, task, with_solution=True)

    ok, detail = task["check"](folder)

    assert ok is True, f"{task_id} reprovou uma solução correta: {detail}"


def test_changing_the_visible_test_is_not_a_valid_fix(tmp_path):
    task = TASKS["corrigir-soma"]
    folder = build(tmp_path, task, with_solution=True)
    (folder / "test_calc.py").write_text("def test_nada():\n    assert True\n", encoding="utf-8")

    ok, detail = task["check"](folder)

    assert ok is False and "test_calc.py" in detail


def test_deleting_the_visible_test_is_not_a_valid_fix(tmp_path):
    task = TASKS["corrigir-estado-compartilhado"]
    folder = build(tmp_path, task, with_solution=True)
    (folder / "test_carrinho.py").unlink()

    assert task["check"](folder)[0] is False


def test_tests_that_miss_the_planted_defects_are_rejected(tmp_path):
    task = TASKS["escrever-testes"]
    folder = build(tmp_path, task)
    (folder / "test_validador.py").write_text(
        "from validador import eh_palindromo\n\n\ndef test_a():\n    assert eh_palindromo('arara')\n\n\n"
        "def test_b():\n    assert not eh_palindromo('python')\n\n\ndef test_c():\n    assert eh_palindromo('osso')\n\n\n"
        "def test_d():\n    assert not eh_palindromo('carro')\n",
        encoding="utf-8",
    )

    ok, detail = task["check"](folder)

    assert ok is False and "não detectam" in detail


def test_tests_that_do_not_even_pass_are_rejected(tmp_path):
    task = TASKS["escrever-testes"]
    folder = build(tmp_path, task)
    (folder / "test_validador.py").write_text(
        "from validador import eh_palindromo\n\n\ndef test_errado():\n    assert eh_palindromo('python')\n    assert 1\n    assert 2\n    assert 3\n",
        encoding="utf-8",
    )

    assert task["check"](folder)[0] is False


def test_changing_the_validator_instead_of_writing_tests_is_rejected(tmp_path):
    task = TASKS["escrever-testes"]
    folder = build(tmp_path, task, with_solution=True)
    (folder / "validador.py").write_text("def eh_palindromo(texto):\n    return True\n", encoding="utf-8")

    ok, detail = task["check"](folder)

    assert ok is False and "alterado" in detail


def test_csv_output_in_the_wrong_order_or_format_is_rejected(tmp_path):
    task = TASKS["resumo-de-csv"]
    folder = build(tmp_path, task)
    (folder / "resumo.py").write_text("print('livros: 50')\nprint('jogos: 60')\nprint('filmes: 15')\n", encoding="utf-8")

    assert task["check"](folder)[0] is False

    (folder / "resumo.py").write_text("print('Total livros = 50')\n", encoding="utf-8")

    assert task["check"](folder)[0] is False


def test_csv_accepts_float_formatting(tmp_path):
    task = TASKS["resumo-de-csv"]
    folder = build(tmp_path, task)
    (folder / "resumo.py").write_text("print('filmes: 15.0')\nprint('jogos: 60.0')\nprint('livros: 50.0')\n", encoding="utf-8")

    assert task["check"](folder)[0] is True


def test_json_with_the_wrong_order_is_rejected(tmp_path):
    task = TASKS["filtrar-json"]
    folder = build(tmp_path, task)
    (folder / "adultos.json").write_text('[{"nome": "Eva", "idade": 45}, {"nome": "Ana", "idade": 30}, {"nome": "Bruno", "idade": 18}]', encoding="utf-8")

    assert task["check"](folder)[0] is False


def test_the_cli_flag_must_not_break_the_plain_mode(tmp_path):
    task = TASKS["adicionar-opcao-cli"]
    folder = build(tmp_path, task)
    (folder / "saudar.py").write_text("import sys\nprint('OLÁ, ' + sys.argv[1].upper() + '!')\n", encoding="utf-8")

    ok, detail = task["check"](folder)

    assert ok is False and "sem a opção" in detail


def test_hardcoding_the_import_fix_by_deleting_the_helper_is_rejected(tmp_path):
    task = TASKS["corrigir-importacao"]
    folder = build(tmp_path, task, with_solution=True)
    (folder / "util" / "helpers.py").write_text("", encoding="utf-8")

    assert task["check"](folder)[0] is False


def test_the_refactor_must_really_use_the_helper(tmp_path):
    task = TASKS["refatorar-duplicacao"]
    folder = build(tmp_path, task)
    (folder / "precos.py").write_text("def com_taxa(valor, taxa):\n    return round(valor * (1 + taxa), 2)\n\n" + task["files"]["precos.py"], encoding="utf-8")

    ok, detail = task["check"](folder)

    assert ok is False and "não usam com_taxa" in detail


def test_battery_exposes_the_real_group_with_approval_and_two_runs():
    cases = [c for c in bateria.CASES if c["group"] == "real"]

    assert len(cases) == 10
    assert all(c["approve"] is True and c["repeat"] == 2 for c in cases)
    assert not any(c["approve"] for c in bateria.CASES if c["group"] != "real")


def test_battery_prompts_point_to_each_task_folder_and_files_are_prepared_there(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    monkeypatch.setattr(bateria, "BATERIA_DIR", tmp_path / "workspace" / "bateria")
    case = next(c for c in bateria.CASES if c["id"] == "corrigir-soma")

    bateria.prepare(case)

    assert "workspace/bateria/real/corrigir-soma" in case["prompt"]
    assert (tmp_path / "workspace/bateria/real/corrigir-soma/calc.py").exists()
    assert (tmp_path / "workspace/bateria/real/corrigir-soma/test_calc.py").exists()


def test_battery_check_of_a_real_task_runs_in_the_right_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(bateria, "ROOT", tmp_path)
    monkeypatch.setattr(bateria, "BATERIA_DIR", tmp_path / "workspace" / "bateria")
    case = next(c for c in bateria.CASES if c["id"] == "adicionar-opcao-cli")

    bateria.prepare(case)
    assert case["check"](None)[0] is False

    (tmp_path / "workspace/bateria/real/adicionar-opcao-cli/saudar.py").write_text(real.SAUDAR_SOLUCAO, encoding="utf-8")

    assert case["check"](None)[0] is True


def test_approving_cases_get_enter_presses_on_stdin_and_the_others_a_closed_stdin(tmp_path, monkeypatch):
    seen = []

    def fake_run(command, **kwargs):
        seen.append(kwargs)
        from types import SimpleNamespace
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(bateria.subprocess, "run", fake_run)
    approving = next(c for c in bateria.CASES if c["id"] == "corrigir-soma")
    cancelling = next(c for c in bateria.CASES if c["id"] == "instalar-cmake")

    bateria.run_in_child_once(approving, 1, tmp_path)
    bateria.run_in_child_once(cancelling, 1, tmp_path)

    assert seen[0].get("input", "").startswith("\n") and "stdin" not in seen[0]
    assert seen[1].get("stdin") == bateria.subprocess.DEVNULL and "input" not in seen[1]
