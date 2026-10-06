import re

from core.paths import PROJECT_ROOT, TAREFAS_DIR

ROTEIRO = PROJECT_ROOT / "ROTEIRO-DE-TESTES.md"


def test_roadmap_exists_and_is_linked_from_manual_and_task_04():
    assert ROTEIRO.exists()

    assert "ROTEIRO-DE-TESTES.md" in (PROJECT_ROOT / "LEIA-ME-WINDOWS.md").read_text(encoding="utf-8")

    task_04 = next(TAREFAS_DIR.glob("tarefa-04-*.md")).read_text(encoding="utf-8")
    assert "ROTEIRO-DE-TESTES.md" in task_04


def test_every_file_the_roadmap_mentions_exists():
    text = ROTEIRO.read_text(encoding="utf-8")

    for relative in re.findall(r"(?:tests|scripts)[/\\][\w./\\-]+\.(?:py|bat)", text):
        assert (PROJECT_ROOT / relative.replace("\\", "/")).exists(), relative

    for name in re.findall(r"\b(\w+\.bat)\b", text):
        assert (PROJECT_ROOT / name).exists(), name


def test_roadmap_covers_the_key_checks():
    text = ROTEIRO.read_text(encoding="utf-8")

    for expected in (
        "ollama --version",
        "verificar.bat",
        "dê continuidade à tarefa 1",
        "test_aceite_tarefa01.py",
        "summarize_logs.py",
        "restaurar.py list",
        "ollama ps",
        "winget",
        "agent.py",
        "test_aceite_tarefa02.py",
        "Tabela de resultados",
    ):
        assert expected in text, expected
