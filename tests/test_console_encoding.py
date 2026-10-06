import contextlib
import io
import sys

import pytest

from core.console import ensure_utf8_console, safe_print
from core.harness import logger
from core.harness.permissions import request_confirmation


class Cp1252Console(io.TextIOWrapper):
    """Imita um console Windows comum, que não consegue mostrar '→' nem emoji."""

    def __init__(self):
        self.raw = io.BytesIO()
        super().__init__(self.raw, encoding="cp1252", errors="strict", write_through=True)


@contextlib.contextmanager
def cp1252_console():
    """
    Instala o console simulado DENTRO do teste (o pytest reinstala o sys.stdout a cada
    fase, então uma fixture de setup seria sobrescrita antes do corpo do teste).
    """

    original = sys.stdout
    console = Cp1252Console()
    sys.stdout = console

    try:
        yield console
    finally:
        sys.stdout = original


def test_plain_print_would_crash_on_cp1252():
    # Confirma que o problema é real neste ambiente simulado.
    with cp1252_console():
        with pytest.raises(UnicodeEncodeError):
            print("⚠️ ação → ok")


def test_safe_print_never_crashes():
    with cp1252_console() as console:
        safe_print("⚠️ ação → ok ✓")

        output = console.raw.getvalue().decode("cp1252")

    assert "ação" in output


def test_log_survives_a_cp1252_console():
    with cp1252_console() as console:
        logger.log("COMPLETION", "continue | próxima transição → candidate → selected")

        written = console.raw.getvalue()

    assert b"COMPLETION" in written


def test_permission_prompt_survives_a_cp1252_console(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "c")

    with cp1252_console() as console:
        answer = request_confirmation("pip install x", "Instalar ⚠️ → agora")

        written = console.raw.getvalue()

    assert answer is False
    assert b"CONFIRMA" in written


def test_ensure_utf8_console_makes_stdout_utf8():
    with cp1252_console() as console:
        ensure_utf8_console()

        print("⚠️ ação → ok")

        written = console.raw.getvalue()

    assert "→".encode("utf-8") in written


def test_batch_launchers_set_utf8():
    from core.paths import PROJECT_ROOT

    for name in ("iniciar.bat", "verificar.bat"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")

        assert "chcp 65001" in text, name
        assert "PYTHONUTF8=1" in text, name


def test_ask_returns_none_on_eof_instead_of_crashing(monkeypatch):
    from core.console import ask

    def raise_eof(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert ask("pergunta: ") is None


def test_user_scripts_do_not_crash_without_a_terminal():
    import subprocess

    from core.paths import PROJECT_ROOT

    # No Windows, stdin=DEVNULL (NUL) até se diz "terminal"; o script não pode dar Traceback.
    result = subprocess.run(
        [sys.executable, "scripts/restaurar.py", "restore", "20260101-000000-000/nao/existe.txt"],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1
