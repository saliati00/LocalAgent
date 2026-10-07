import pytest

import core.backups as backups
from core.paths import BACKUPS_DIR, PROJECT_ROOT, TMP_ROOT
from tools.filesystem import is_path_writable, replace_in_file, write_file


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    store = tmp_path / "backups"

    monkeypatch.setattr(backups, "PROJECT_ROOT", root)
    monkeypatch.setattr(backups, "BACKUPS_DIR", store)

    return root, store


def test_backup_copies_an_existing_file_with_its_relative_path(sandbox):
    root, store = sandbox
    (root / "pasta").mkdir()
    target = root / "pasta" / "a.txt"
    target.write_text("versao 1", encoding="utf-8")

    backup_id = backups.backup_file(target)

    assert backup_id.endswith("/pasta/a.txt")
    assert (store / backup_id).read_text(encoding="utf-8") == "versao 1"


def test_no_backup_for_missing_or_huge_files(sandbox, monkeypatch):
    root, _ = sandbox

    assert backups.backup_file(root / "nao_existe.txt") is None

    big = root / "grande.bin"
    big.write_bytes(b"x" * 100)
    monkeypatch.setattr(backups, "MAX_BACKUP_BYTES", 10)

    assert backups.backup_file(big) is None


def test_list_is_newest_first_and_restore_brings_the_old_content_back(sandbox):
    root, store = sandbox
    target = root / "a.txt"

    target.write_text("um", encoding="utf-8")
    first = backups.backup_file(target)
    target.write_text("dois", encoding="utf-8")
    second = backups.backup_file(target)
    target.write_text("tres", encoding="utf-8")

    listed = [item["id"] for item in backups.list_backups()]
    assert listed[:2] == [second, first]

    result = backups.restore_backup(first)

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "um"

    # restaurar também guardou a versão que estava lá ("tres")
    contents = {(store / item["id"]).read_text(encoding="utf-8") for item in backups.list_backups()}
    assert "tres" in contents


@pytest.mark.parametrize("bad_id", ["", "sem-barra", "20260101-000000-000/../fora.txt", "inexistente/a.txt"])
def test_restore_rejects_bad_ids(sandbox, bad_id):
    assert backups.restore_backup(bad_id)["success"] is False


def test_prune_keeps_only_the_most_recent_folders(sandbox):
    _, store = sandbox

    for index in range(5):
        folder = store / f"2026010{index}-000000-000"
        folder.mkdir(parents=True)
        (folder / "a.txt").write_text(str(index), encoding="utf-8")

    backups.prune(max_dirs=2)

    assert sorted(p.name for p in store.iterdir()) == ["20260103-000000-000", "20260104-000000-000"]


def test_write_file_and_replace_in_file_back_up_before_overwriting(tmp_path, monkeypatch):
    store = tmp_path / "backups"
    monkeypatch.setattr(backups, "BACKUPS_DIR", store)

    target = TMP_ROOT / "localagent_backup_test.txt"
    target.write_text("original", encoding="utf-8")

    try:
        assert write_file(str(target), "novo")["success"] is True
        assert replace_in_file(str(target), "novo", "mais novo")["success"] is True

        saved = sorted(p.read_text(encoding="utf-8") for p in store.rglob("*") if p.is_file())

        assert saved == ["novo", "original"]
        assert target.read_text(encoding="utf-8") == "mais novo"
    finally:
        target.unlink(missing_ok=True)


def test_new_files_are_not_backed_up(tmp_path, monkeypatch):
    store = tmp_path / "backups"
    monkeypatch.setattr(backups, "BACKUPS_DIR", store)

    target = TMP_ROOT / "localagent_backup_new.txt"
    target.unlink(missing_ok=True)

    try:
        assert write_file(str(target), "primeira versao")["success"] is True
        assert not store.exists() or not list(store.rglob("*.txt"))
    finally:
        target.unlink(missing_ok=True)


def test_backups_dir_is_protected_from_the_agent():
    writable, _ = is_path_writable(BACKUPS_DIR / "20260101-000000-000" / "a.txt")
    assert writable is False

    assert write_file(str(PROJECT_ROOT / "backups" / "x.txt"), "x")["success"] is False


def test_two_backups_of_the_same_file_in_the_same_instant_do_not_overwrite_each_other(sandbox, monkeypatch):
    from datetime import datetime as real_datetime

    root, store = sandbox

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 10, 7, 8, 30, 6, 428000)

    monkeypatch.setattr(backups, "datetime", FrozenDatetime)

    target = root / "a.txt"

    target.write_text("um", encoding="utf-8")
    first = backups.backup_file(target)
    target.write_text("dois", encoding="utf-8")
    second = backups.backup_file(target)

    assert first != second
    assert (store / first).read_text(encoding="utf-8") == "um"
    assert (store / second).read_text(encoding="utf-8") == "dois"
    assert [item["id"] for item in backups.list_backups()] == [second, first]
