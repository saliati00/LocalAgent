import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import agent
import core.tasks as tasks
from core.paths import PROJECT_ROOT, TAREFAS_DIR
from scripts import summarize_logs
from tools.filesystem import is_path_writable, write_file

FORBIDDEN_DEV_WORDS = ("continue", "desenvolvimento", "projeto.md", "checklist")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    tarefas = tmp_path / "tarefas"
    workspace = tmp_path / "workspace"
    tarefas.mkdir()
    workspace.mkdir()
    (tarefas / "tarefa-02-exemplo.md").write_text("# Tarefa 02 — Exemplo\nFaça X.", encoding="utf-8")

    monkeypatch.setattr(tasks, "TAREFAS_DIR", tarefas)
    monkeypatch.setattr(tasks, "WORKSPACE_DIR", workspace)

    return tarefas, workspace


# ---------------------------------------------------------
# Reconhecimento do pedido
# ---------------------------------------------------------

@pytest.mark.parametrize("text, number", [
    ("dê continuidade à tarefa 2", 2),
    ("de continuidade a tarefa2", 2),
    ("Retome a tarefa-03", 3),
    ("@tarefa2", 2),
    ("@Tarefa 02", 2),
    ("execute a tarefa 12", 12),
    ("faça a tarefa 1 agora", 1),
])
def test_find_task_number_recognizes_natural_requests(text, number):
    assert tasks.find_task_number(text) == number


@pytest.mark.parametrize("text", [
    "Verifique se o git está instalado",
    "o que é a tarefa 3 do manual?",
    "tarefa 2",
    "Crie um arquivo tarefa.txt",
])
def test_find_task_number_ignores_ordinary_text(text):
    assert tasks.find_task_number(text) is None


# ---------------------------------------------------------
# Montagem do prompt
# ---------------------------------------------------------

def test_prompt_contains_task_user_request_and_no_progress_note(isolated):
    ok, prompt = tasks.build_task_prompt(2, "dê continuidade à tarefa 2")

    assert ok is True
    assert prompt.startswith("[TAREFA 02]")
    assert "Faça X." in prompt
    assert "PEDIDO DO USUÁRIO: dê continuidade à tarefa 2" in prompt
    assert "nenhum. Comece pelo passo 1" in prompt


def test_prompt_resumes_from_saved_progress(isolated):
    _, workspace = isolated
    (workspace / "tarefa-02").mkdir()
    (workspace / "tarefa-02" / "progresso.md").write_text("[passo 1] feito: criei a pasta", encoding="utf-8")

    ok, prompt = tasks.build_task_prompt(2, "continuidade")

    assert "continue a partir daqui" in prompt
    assert "[passo 1] feito: criei a pasta" in prompt


def test_long_progress_keeps_only_the_most_recent_part(isolated):
    _, workspace = isolated
    (workspace / "tarefa-02").mkdir()
    (workspace / "tarefa-02" / "progresso.md").write_text("antigo " * 1000 + "ULTIMA-LINHA", encoding="utf-8")

    progress = tasks.read_progress(2)

    assert "ULTIMA-LINHA" in progress
    assert len(progress) < tasks.MAX_PROGRESS_CHARS + 50


def test_missing_task_lists_the_available_ones(isolated):
    ok, message = tasks.build_task_prompt(9, "x")

    assert ok is False
    assert "2" in message


# ---------------------------------------------------------
# Integração com o agent
# ---------------------------------------------------------

def test_resolve_prompt_loads_task_and_missing_task_returns_none(isolated):
    assert agent.resolve_prompt("dê continuidade à tarefa 2").startswith("[TAREFA 02]")
    assert agent.resolve_prompt("@tarefa9") is None
    assert agent.resolve_prompt("Verifique o git") == "Verifique o git"


def test_numbered_task_prompt_does_not_trigger_the_checklist_development_flow(isolated, tmp_path, monkeypatch):
    seen = {}

    def fake_chat(*args, **kwargs):
        seen["user"] = kwargs["messages"][1]["content"]
        return SimpleNamespace(
            message=SimpleNamespace(role="assistant", content="ok", tool_calls=None),
            prompt_eval_count=10,
            eval_count=5,
        )

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    monkeypatch.setattr(agent, "TASKS_DIR", tmp_path / "saida")
    monkeypatch.setattr(agent, "check_completion", lambda **kw: {"status": "complete", "reason": "ok"})

    prompt = agent.resolve_prompt("continue a tarefa 2")
    agent.agent(prompt)

    assert "ETAPA IMEDIATA DE DESENVOLVIMENTO" not in seen["user"]
    assert seen["user"].startswith("[TAREFA 02]")


# ---------------------------------------------------------
# Arquivos reais de tarefas
# ---------------------------------------------------------

def real_task_files():
    return sorted(TAREFAS_DIR.glob("tarefa-*.md"))


def test_real_tasks_exist_and_follow_the_structure():
    files = real_task_files()

    assert len(files) >= 5

    for path in files:
        text = path.read_text(encoding="utf-8")

        for section in ("## Objetivo", "## Pronto quando"):
            assert section in text, f"{path.name}: falta '{section}'"

        assert text.startswith("# Tarefa "), path.name
        assert "Quem faz:" in text, path.name
        assert len(text) < 3500, f"{path.name}: grande demais para o contexto"


def test_real_task_numbers_are_sequential_and_unique():
    numbers = [n for n, _ in tasks.list_tasks()]

    assert numbers == list(range(1, len(numbers) + 1))


def test_agent_tasks_have_acceptance_tests_and_progress_file():
    for number, name in tasks.list_tasks():
        text = (TAREFAS_DIR / name).read_text(encoding="utf-8")

        if "Quem faz: agente" in text:
            assert (PROJECT_ROOT / "tests" / f"test_aceite_tarefa{number:02d}.py").exists(), name
            assert f"workspace/tarefa-{number:02d}/progresso.md" in text, name


# ---------------------------------------------------------
# Proteções
# ---------------------------------------------------------

@pytest.mark.parametrize("relative", [
    "tarefas/tarefa-01-verificar-ambiente.md",
    "tarefas/nova.md",
    "scripts/promote_skill.py",
    "scripts/setup_windows.ps1",
    "instalar.bat",
    "iniciar.bat",
    "verificar.bat",
    "requirements.txt",
])
def test_user_owned_files_are_protected_from_the_agent(relative):
    writable, _ = is_path_writable(PROJECT_ROOT / relative)
    assert writable is False


@pytest.mark.parametrize("relative", [
    "scripts/eval/runner.py",
    "scripts/eval/tarefas/novo.json",
    "workspace/tarefa-01/ambiente.md",
    "workspace/tarefa-02/progresso.md",
])
def test_task_deliverable_paths_are_writable(relative):
    writable, error = is_path_writable(PROJECT_ROOT / relative)
    assert writable is True, error


# ---------------------------------------------------------
# Testes de aceite: ficam fora da suíte normal e falham até o trabalho existir
# ---------------------------------------------------------

def run_acceptance(file_name):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "aceite", f"tests/{file_name}", "-q", "-p", "no:cacheprovider"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("file_name", [
    "test_aceite_tarefa01.py",
    "test_aceite_tarefa02.py",
    "test_aceite_tarefa03.py",
])
def test_acceptance_tests_are_collected_only_on_request(file_name):
    result = run_acceptance(file_name)

    # Com o trabalho ainda por fazer, o aceite precisa FALHAR (não pode passar vazio)
    # e nunca pode dar erro de coleta/sintaxe (exit code 2/4).
    assert result.returncode in (0, 1), result.stdout + result.stderr


def test_default_suite_deselects_acceptance_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_aceite_tarefa01.py", "-q", "-p", "no:cacheprovider"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert "deselected" in result.stdout or "no tests ran" in result.stdout


def test_acceptance_run_is_safe_for_the_agent_without_confirmation():
    from core.harness.permissions import requires_confirmation

    assert requires_confirmation("pytest -m aceite tests/test_aceite_tarefa01.py -q") is False


# ---------------------------------------------------------
# summarize_logs
# ---------------------------------------------------------

def test_summarize_logs_reads_new_and_old_formats():
    sizes = json.dumps({
        "system_instructions": {"chars": 900, "est_tokens": 300},
        "tools_schema": {"chars": 600, "est_tokens": 200},
        "_total": {"chars": 1500, "est_tokens": 500},
    })

    lines = [
        "[2026-10-06 10:00:00] [abcd1234] RUN_START | run_id=abcd1234",
        f"[2026-10-06 10:00:01] [abcd1234] PROMPT_SIZES | {sizes}",
        "[2026-10-06 10:00:02] [abcd1234] TOKENS | input=4000 | output=50 | total=4050",
        "[2026-10-06 10:00:03] [abcd1234] CONTEXT_NEAR_LIMIT | prompt=7900 de 8192",
        "[2026-10-06 10:00:04] TOKENS | input=6000 | output=20 | total=6020",
        "linha solta sem formato",
    ]

    report = summarize_logs.summarize(lines)

    assert report["runs"] == 1
    assert report["model_calls"] == 2
    assert report["input_tokens"]["max"] == 6000
    assert report["prompt_estimate_tokens"]["avg"] == 500
    assert report["prompt_sections_avg_tokens"]["tools_schema"] == 200
    assert report["events"]["CONTEXT_NEAR_LIMIT"] == 1
