"""Nada a anotar à mão: tudo o que o usuário precisaria informar sai na pasta logs."""

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bateria  # noqa: E402
import comparar_modelos as cmp  # noqa: E402
import estimar_desempenho as est  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402


# ---------------------------------------------------------
# A tela de confirmação deixou de depender de olho humano
# ---------------------------------------------------------

def test_confirmation_screen_is_checked_automatically_in_both_console_encodings():
    ok, detail = bateria.confirmation_screen_check(None)

    assert ok is True, detail
    assert "cp1252" in detail and "utf-8" in detail


def test_the_screen_case_is_part_of_the_battery_and_never_runs_the_model():
    case = next(c for c in bateria.CASES if c["id"] == "tela-de-confirmacao")

    assert case["kind"] == "tela" and case["group"] == "seguranca" and case["approve"] is False


def test_a_broken_confirmation_screen_is_reported_not_swallowed(monkeypatch):
    def broken(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout=b"", stderr="UnicodeEncodeError: charmap".encode())

    monkeypatch.setattr(bateria.subprocess, "run", broken)

    ok, detail = bateria.confirmation_screen_check(None)

    assert ok is False and "quebrou" in detail


def test_an_incomplete_screen_is_rejected(monkeypatch):
    monkeypatch.setattr(bateria.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"RESULTADO False", stderr=b""))

    ok, detail = bateria.confirmation_screen_check(None)

    assert ok is False and "incompleta" in detail


# ---------------------------------------------------------
# console.txt: nada precisa ser copiado da tela
# ---------------------------------------------------------

def test_tee_mirrors_everything_printed_into_a_file(tmp_path):
    target = io.StringIO()
    tee = cmp.Tee(target, tmp_path / "console.txt")

    tee.write("primeira linha\n")
    tee.write("açúcar e emoji ⚠️\n")
    tee.flush()
    tee.close()

    assert target.getvalue() == "primeira linha\naçúcar e emoji ⚠️\n"
    assert (tmp_path / "console.txt").read_text(encoding="utf-8") == target.getvalue()


def test_tee_survives_an_unwritable_file_and_a_console_that_cannot_encode(tmp_path):
    class Ascii(io.StringIO):
        def write(self, text):
            if any(ord(c) > 127 for c in text):
                raise UnicodeEncodeError("ascii", text, 0, 1, "x")

            return super().write(text)

    target = Ascii()
    tee = cmp.Tee(target, tmp_path / "nao-existe" / "console.txt")

    tee.write("ação\n")

    assert "a" in target.getvalue() and tee.handle is None


def test_the_child_output_is_echoed_through_the_terminal_so_it_lands_in_console_txt(monkeypatch):
    printed = io.StringIO()
    monkeypatch.setattr(cmp.sys, "stdout", printed)
    seen = {}

    class Process:
        pid = 1
        stdout = io.StringIO("[1/43] criar-arquivo (rodada 1) ... passou\n")

        def wait(self, timeout=None):
            import time
            time.sleep(0.2)
            return 0

        def kill(self):
            pass

    def popen(command, **kwargs):
        seen.update(kwargs)
        return Process()

    assert cmp.run_guarded(["x"], {}, ".", 100, memory=lambda: 8000, popen=popen, poll=1, echo=True) == "ok"

    import time
    time.sleep(0.3)

    assert seen["stdout"] == cmp.subprocess.PIPE and seen["stderr"] == cmp.subprocess.STDOUT
    assert "criar-arquivo" in printed.getvalue()


def test_run_one_asks_for_the_echo(tmp_path, monkeypatch):
    flags = {}
    monkeypatch.setattr(cmp, "run_guarded", lambda *a, **k: flags.update(k) or "ok")
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: None)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)

    cmp.run_one(cmp.profile_from_model("m"), tmp_path, SimpleNamespace(repeticoes=1, rapido=False, limite_modelo=5))

    assert flags["echo"] is True


def test_an_unexpected_error_is_saved_in_logs_with_the_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cmp, "ROOT", tmp_path)

    def explode(args):
        raise RuntimeError("falha esquisita")

    monkeypatch.setattr(cmp, "orchestrate", explode)

    assert cmp.main(["--perfis", "9b"]) == 1

    report = (tmp_path / "logs" / "comparar-erro.txt").read_text(encoding="utf-8")

    assert "RuntimeError: falha esquisita" in report and "Traceback" in report
    assert "comparar-erro.txt" in capsys.readouterr().out


# ---------------------------------------------------------
# maquina.txt e logs do Ollama
# ---------------------------------------------------------

def fake_run(command, timeout=60):
    text = " ".join(command)

    if "nvidia-smi" in text:
        return 0, "NVIDIA GeForce RTX 3070, 551.23, 8192 MiB"

    if "--version" in text:
        return 0, "ollama version is 0.40.1"

    if "list" in text:
        return 0, "NAME ID SIZE\nqwen3.5:9b abc 6.6 GB"

    if "powercfg" in text:
        return 0, "GUID do plano: x (Alto desempenho)"

    return 0, "abc123"


def test_the_machine_sheet_has_everything_the_user_used_to_report_by_hand():
    sheet = cmp.machine_snapshot(run=fake_run, profiles=[{"label": "9b"}, {"label": "4b"}])

    for expected in ("RTX 3070", "551.23", "ollama version is 0.40.1", "qwen3.5:9b", "Python:", "Disco livre", "RAM total",
                     "Variáveis OLLAMA_*", "abc123", "9b, 4b"):
        assert expected in sheet, expected


def test_missing_tools_show_as_unavailable_instead_of_failing():
    sheet = cmp.machine_snapshot(run=lambda command, timeout=60: (1, "não achei"))

    assert "(não disponível)" in sheet and "FICHA DA MÁQUINA" in sheet


def test_the_tail_of_the_ollama_logs_is_copied_into_the_run_folder(tmp_path):
    source = tmp_path / "Ollama"
    source.mkdir()
    (source / "server.log").write_text("\n".join(f"linha {i}" for i in range(5000)), encoding="utf-8")
    (source / "app.log").write_text("app ok", encoding="utf-8")
    destination = tmp_path / "run"
    destination.mkdir()

    copied = cmp.collect_ollama_logs(destination, tail_lines=100, base=source)

    tail = (destination / "ollama-server.log").read_text(encoding="utf-8").splitlines()

    assert copied == ["server.log", "app.log"]
    assert len(tail) == 100 and tail[-1] == "linha 4999" and (destination / "ollama-app.log").exists()


def test_missing_ollama_logs_are_ignored(tmp_path):
    assert cmp.collect_ollama_logs(tmp_path, base=tmp_path / "nao-existe") == []


# ---------------------------------------------------------
# Estimativa e instalação também em logs/
# ---------------------------------------------------------

def test_the_estimate_is_saved_in_logs_by_default_and_in_the_chosen_file_when_asked(tmp_path, capsys):
    assert est.DEFAULT_OUTPUT == PROJECT_ROOT / "logs" / "estimativa-desempenho.txt"

    target = tmp_path / "logs" / "estimativa.txt"
    est.main(["--saida", str(target)])

    assert "VALIDAÇÃO" in target.read_text(encoding="utf-8")
    assert "salvo em" in capsys.readouterr().out


def test_the_installer_writes_its_log_inside_logs():
    script = (PROJECT_ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $LogDir "instalacao.log"' in script and 'Join-Path $Root "logs"' in script
    assert "New-Item -ItemType Directory -Force $LogDir" in script


def test_the_home_checklist_asks_for_nothing_but_the_logs_folder():
    text = (PROJECT_ROOT / "FAZER-EM-CASA.txt").read_text(encoding="utf-8")

    assert "NAO precisa anotar nem copiar nada" in text
    assert "ollama --version" not in text, "a versão do Ollama agora vem do maquina.txt"
    assert "Apareceu legivel" not in text, "a tela de confirmação agora é verificada pela bateria"
    assert "maquina.txt" in text and "console.txt" in text and "consumo.csv" in text
