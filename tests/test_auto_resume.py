"""O comparar.bat continua sozinho a rodada que não terminou: sem precisar lembrar a pasta nem a opção."""

import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402

NOW = datetime.datetime(2026, 10, 12, 9, 0, 0)


def make_run(base, name, perfis, concluida=False, started=NOW - datetime.timedelta(hours=2), **extra):
    folder = base / name
    folder.mkdir(parents=True)
    data = {"perfis": perfis, "rapido": False, "repeticoes": 2, "limite_modelo": 6000,
            "iniciada": started.isoformat(timespec="seconds"), "concluida": concluida, **extra}
    (folder / cmp.RUN_FILE).write_text(json.dumps(data), encoding="utf-8")
    return folder


# ---------------------------------------------------------
# Escolha da rodada a continuar
# ---------------------------------------------------------

def test_the_newest_unfinished_run_with_the_same_profiles_is_picked(tmp_path):
    make_run(tmp_path, "20261010_220000", ["9b", "4b"])
    newest = make_run(tmp_path, "20261011_220000", ["9b", "4b"])

    found = cmp.find_unfinished(["9b", "4b"], base=tmp_path, now=NOW)

    assert found[0] == newest and found[1]["perfis"] == ["9b", "4b"]


def test_finished_runs_are_never_resumed(tmp_path):
    make_run(tmp_path, "20261011_220000", ["9b", "4b"], concluida=True)

    assert cmp.find_unfinished(["9b", "4b"], base=tmp_path, now=NOW) is None


def test_a_run_for_different_profiles_is_not_resumed(tmp_path):
    make_run(tmp_path, "20261011_220000", ["9b", "4b"])

    assert cmp.find_unfinished(["9b"], base=tmp_path, now=NOW) is None
    assert cmp.find_unfinished(["4b", "9b"], base=tmp_path, now=NOW) is None


def test_runs_older_than_a_week_are_ignored(tmp_path):
    make_run(tmp_path, "20261001_220000", ["9b"], started=NOW - datetime.timedelta(days=8))

    assert cmp.find_unfinished(["9b"], base=tmp_path, now=NOW) is None


def test_a_newer_finished_run_does_not_hide_an_older_unfinished_one(tmp_path):
    older = make_run(tmp_path, "20261010_220000", ["9b"])
    make_run(tmp_path, "20261011_220000", ["9b"], concluida=True)

    assert cmp.find_unfinished(["9b"], base=tmp_path, now=NOW)[0] == older


def test_corrupt_or_missing_run_files_are_skipped(tmp_path):
    broken = tmp_path / "20261011_220000"
    broken.mkdir()
    (broken / cmp.RUN_FILE).write_text("{quebrado", encoding="utf-8")
    (tmp_path / "20261011_230000").mkdir()
    good = make_run(tmp_path, "20261010_220000", ["9b"])

    assert cmp.find_unfinished(["9b"], base=tmp_path, now=NOW)[0] == good
    assert cmp.find_unfinished(["9b"], base=tmp_path / "nao-existe", now=NOW) is None


# ---------------------------------------------------------
# O fluxo completo
# ---------------------------------------------------------

@pytest.fixture
def world(tmp_path, monkeypatch):
    """Um projeto falso: sem Ollama de verdade, run_model registra o que recebeu."""

    calls = []

    def fake_run_model(profile, root, args, entries, resume, ensure):
        calls.append({"label": profile["label"], "root": root, "resume": resume, "rapido": args.rapido, "repeticoes": args.repeticoes})

    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(cmp, "ROOT", tmp_path)
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60, env=None: (0, "ollama version is 9.9"))
    monkeypatch.setattr(cmp, "model_installed", lambda m: True)
    monkeypatch.setattr(cmp, "run_model", fake_run_model)

    return SimpleNamespace(root=tmp_path / "logs" / "comparacao", calls=calls)


def args(**overrides):
    base = dict(modelos="", perfis="9b,4b", base=None, base_nome="x", retomar=None, nova=False, sim=True,
                rapido=False, repeticoes=2, limite_modelo=6000)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_running_again_continues_the_unfinished_run_with_its_original_options(world, capsys):
    old = make_run(world.root, "20261010_220000", ["9b", "4b"], rapido=True, repeticoes=3,
                   started=datetime.datetime.now() - datetime.timedelta(hours=3))

    cmp.orchestrate(args())

    assert [c["root"] for c in world.calls] == [old, old]
    assert all(c["resume"] is True and c["rapido"] is True and c["repeticoes"] == 3 for c in world.calls)
    assert "Continuando de onde parou" in capsys.readouterr().out
    assert len(list(world.root.iterdir())) == 1, "não pode criar uma pasta nova"


def test_a_finished_run_is_marked_complete_so_the_next_run_starts_fresh(world):
    cmp.orchestrate(args())

    folders = list(world.root.iterdir())

    assert len(folders) == 1
    assert json.loads((folders[0] / cmp.RUN_FILE).read_text(encoding="utf-8"))["concluida"] is True
    assert all(c["resume"] is False for c in world.calls)

    world.calls.clear()
    cmp.orchestrate(args())

    assert all(c["resume"] is False for c in world.calls) and all(c["root"] != folders[0] for c in world.calls)


def test_a_run_that_fails_midway_is_left_resumable(world, monkeypatch):
    def dies(profile, root, a, entries, resume, ensure):
        raise KeyboardInterrupt

    monkeypatch.setattr(cmp, "run_model", dies)
    cmp.orchestrate(args())

    folder = next(world.root.iterdir())

    assert json.loads((folder / cmp.RUN_FILE).read_text(encoding="utf-8"))["concluida"] is False

    monkeypatch.undo()
    # refaz o ambiente falso (o undo desfez tudo) e confirma que a próxima execução continua desta pasta
    seen = []
    monkeypatch.setattr(bateria, "ensure_ollama", lambda wait_seconds=90: True)
    monkeypatch.setattr(cmp, "ROOT", world.root.parent.parent)
    monkeypatch.setattr(cmp, "run_cmd", lambda command, timeout=60, env=None: (0, "ollama version is 9.9"))
    monkeypatch.setattr(cmp, "model_installed", lambda m: True)
    monkeypatch.setattr(cmp, "run_model", lambda profile, root, a, entries, resume, ensure: seen.append((root, resume)))

    cmp.orchestrate(args())

    assert {root for root, _ in seen} == {folder} and all(resume for _, resume in seen)


def test_the_new_flag_ignores_the_unfinished_run(world):
    old = make_run(world.root, "20261010_220000", ["9b", "4b"], started=datetime.datetime.now() - datetime.timedelta(hours=1))

    cmp.orchestrate(args(nova=True))

    assert all(c["root"] != old and c["resume"] is False for c in world.calls)


def test_an_explicit_resume_folder_wins_over_the_automatic_search(world):
    other = make_run(world.root, "20261009_220000", ["9b", "4b"], started=datetime.datetime.now() - datetime.timedelta(hours=5))
    make_run(world.root, "20261010_220000", ["9b", "4b"], started=datetime.datetime.now() - datetime.timedelta(hours=1))

    cmp.orchestrate(args(retomar=str(other)))

    assert all(c["root"] == other and c["resume"] is True for c in world.calls)


def test_different_profiles_start_a_new_run_even_if_an_older_one_is_unfinished(world):
    old = make_run(world.root, "20261010_220000", ["9b", "4b"], started=datetime.datetime.now() - datetime.timedelta(hours=1))

    cmp.orchestrate(args(perfis="4b"))

    assert all(c["root"] != old and c["resume"] is False for c in world.calls)


def test_the_run_file_records_what_was_asked(world):
    cmp.orchestrate(args(rapido=True, repeticoes=1))

    data = json.loads((next(world.root.iterdir()) / cmp.RUN_FILE).read_text(encoding="utf-8"))

    assert data["perfis"] == ["9b", "4b"] and data["rapido"] is True and data["repeticoes"] == 1
