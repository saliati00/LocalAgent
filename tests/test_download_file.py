from contextlib import contextmanager

import tools.web as web
from core.paths import TMP_ROOT


class FakeResponse:
    def __init__(self, status_code=200, chunks=(b"abc", b"def"), fail_after=None):
        self.status_code = status_code
        self._chunks = chunks
        self._fail_after = fail_after

    def iter_bytes(self, chunk_size=16384):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise RuntimeError("conexão perdida")
            yield chunk


def patch_stream(monkeypatch, response):
    @contextmanager
    def fake_stream(*args, **kwargs):
        yield response

    monkeypatch.setattr(web.httpx, "stream", fake_stream)


def test_download_success_writes_file_without_part_leftover(monkeypatch, tmp_path):
    patch_stream(monkeypatch, FakeResponse())
    dest = TMP_ROOT / "localagent_dl_ok.bin"
    dest.unlink(missing_ok=True)

    result = web.download_file("https://example.com/a.bin", str(dest))

    try:
        assert result["success"] is True
        assert dest.read_bytes() == b"abcdef"
        assert not dest.with_name(dest.name + ".part").exists()
    finally:
        dest.unlink(missing_ok=True)


def test_download_failure_leaves_no_partial_file(monkeypatch):
    patch_stream(monkeypatch, FakeResponse(chunks=(b"abc", b"def"), fail_after=1))
    dest = TMP_ROOT / "localagent_dl_fail.bin"
    dest.unlink(missing_ok=True)

    result = web.download_file("https://example.com/a.bin", str(dest))

    assert result["success"] is False
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_respects_size_limit(monkeypatch):
    monkeypatch.setattr(web, "MAX_DOWNLOAD_BYTES", 4)
    patch_stream(monkeypatch, FakeResponse(chunks=(b"abc", b"def")))
    dest = TMP_ROOT / "localagent_dl_big.bin"
    dest.unlink(missing_ok=True)

    result = web.download_file("https://example.com/a.bin", str(dest))

    assert result["success"] is False
    assert "limite" in result["error"].lower()
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_refuses_protected_destination(monkeypatch):
    patch_stream(monkeypatch, FakeResponse())

    result = web.download_file("https://example.com/a.bin", "specs/projeto.md")

    assert result["success"] is False
