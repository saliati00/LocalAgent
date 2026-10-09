"""Monitor de consumo da máquina: leitura da GPU, gravação à prova de travamento e resumo no relatório."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import comparar_modelos as cmp  # noqa: E402


# ---------------------------------------------------------
# nvidia-smi
# ---------------------------------------------------------

def test_gpu_line_is_parsed_into_named_values():
    gpu = cmp.read_gpu(lambda command, timeout=60: (0, "7123, 8192, 97, 120.55, 71"))

    assert gpu == {"vram_usada_mb": 7123.0, "vram_total_mb": 8192.0, "gpu_pct": 97.0, "potencia_w": 120.55, "temp_c": 71.0}


def test_unavailable_fields_are_left_out_instead_of_breaking_the_reading():
    gpu = cmp.read_gpu(lambda command, timeout=60: (0, "7123, 8192, 97, [N/A], 71"))

    assert "potencia_w" not in gpu and gpu["vram_usada_mb"] == 7123.0


def test_a_machine_without_nvidia_smi_or_with_garbage_output_gives_an_empty_reading():
    assert cmp.read_gpu(lambda command, timeout=60: (1, "nvidia-smi não encontrado")) == {}
    assert cmp.read_gpu(lambda command, timeout=60: (0, "")) == {}
    assert cmp.read_gpu(lambda command, timeout=60: (0, "isso, não, é, csv")) == {}
    assert cmp.read_gpu(lambda command, timeout=60: (0, "1, 2")) == {}


def test_the_first_cpu_reading_is_none_and_the_next_is_a_percentage():
    meter = cmp.CpuMeter()

    assert meter.read() is None

    value = meter.read()

    assert value is None or 0 <= value <= 100


# ---------------------------------------------------------
# Amostra e gravação
# ---------------------------------------------------------

def test_a_sample_combines_ram_gpu_and_cpu_and_skips_what_cannot_be_read():
    sample = cmp.sample_resources(memory=lambda: 5000, gpu=lambda: {"vram_usada_mb": 6000.0, "gpu_pct": 80.0},
                                  cpu=lambda: 33.3, clock=lambda: "10:00:00")

    assert sample == {"hora": "10:00:00", "ram_livre_mb": 5000, "vram_usada_mb": 6000.0, "gpu_pct": 80.0, "cpu_pct": 33.3}

    bare = cmp.sample_resources(memory=lambda: None, gpu=lambda: {}, cpu=None, clock=lambda: "10:00:05")

    assert bare == {"hora": "10:00:05"}


def test_samples_are_appended_with_one_header_and_forced_to_disk(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr(cmp.os, "fsync", lambda fd: synced.append(fd))
    target = tmp_path / "consumo.csv"

    cmp.append_sample(target, {"hora": "10:00:00", "ram_livre_mb": 5000, "vram_usada_mb": 6000.0})
    cmp.append_sample(target, {"hora": "10:00:05", "ram_livre_mb": 4800, "extra": "ignorado"})

    lines = target.read_text(encoding="utf-8").splitlines()

    assert lines[0] == ",".join(cmp.CONSUMPTION_COLUMNS)
    assert lines[1].startswith("10:00:00,5000,6000.0") and lines[2].startswith("10:00:05,4800,")
    assert len(lines) == 3 and len(synced) == 2


def test_an_unwritable_destination_does_not_raise(tmp_path):
    cmp.append_sample(tmp_path / "nao-existe" / "consumo.csv", {"hora": "x"})


def write_samples(path, rows):
    for row in rows:
        cmp.append_sample(path, row)


def test_the_summary_reports_peaks_averages_and_the_lowest_free_memory(tmp_path):
    target = tmp_path / "consumo.csv"
    write_samples(target, [
        {"hora": "1", "ram_livre_mb": 6000, "vram_usada_mb": 5000.0, "vram_total_mb": 8192.0, "gpu_pct": 40.0, "potencia_w": 90.0, "temp_c": 60.0, "cpu_pct": 10.0},
        {"hora": "2", "ram_livre_mb": 900, "vram_usada_mb": 7800.0, "vram_total_mb": 8192.0, "gpu_pct": 100.0, "potencia_w": 150.0, "temp_c": 78.0, "cpu_pct": 30.0},
        {"hora": "3", "ram_livre_mb": 3000, "vram_usada_mb": 7000.0, "vram_total_mb": 8192.0, "gpu_pct": 70.0, "potencia_w": 120.0, "temp_c": 74.0},
    ])

    summary = cmp.summarize_consumption(target)

    assert summary["amostras"] == 3
    assert summary["vram_pico_mb"] == 7800.0 and summary["vram_total_mb"] == 8192.0
    assert summary["gpu_medio_pct"] == 70.0 and summary["gpu_pico_pct"] == 100.0
    assert summary["potencia_pico_w"] == 150.0 and summary["temp_pico_c"] == 78.0
    assert summary["ram_livre_min_mb"] == 900.0 and summary["cpu_medio_pct"] == 20.0


def test_the_summary_handles_missing_files_empty_files_and_missing_columns(tmp_path):
    assert cmp.summarize_consumption(tmp_path / "nao-existe.csv") is None

    (tmp_path / "vazio.csv").write_text(",".join(cmp.CONSUMPTION_COLUMNS) + "\n", encoding="utf-8")
    assert cmp.summarize_consumption(tmp_path / "vazio.csv") is None

    no_gpu = tmp_path / "sem-gpu.csv"
    write_samples(no_gpu, [{"hora": "1", "ram_livre_mb": 4000}, {"hora": "2", "ram_livre_mb": 3500}])
    summary = cmp.summarize_consumption(no_gpu)

    assert summary["vram_pico_mb"] is None and summary["gpu_medio_pct"] is None and summary["ram_livre_min_mb"] == 3500.0


# ---------------------------------------------------------
# Ligação com o vigia e com o relatório
# ---------------------------------------------------------

class FakeProcess:
    def __init__(self, polls_before_exit):
        self.pid = 1
        self.remaining = polls_before_exit

    def wait(self, timeout=None):
        if self.remaining <= 0:
            return 0

        self.remaining -= 1
        raise subprocess.TimeoutExpired("x", timeout)

    def kill(self):
        pass


def test_the_watchdog_samples_on_every_cycle(tmp_path):
    seen = []

    outcome = cmp.run_guarded(["x"], {}, ".", 1000, memory=lambda: 8000, popen=lambda *a, **k: FakeProcess(3),
                              clock=lambda: 0, poll=1, sampler=lambda: seen.append(1))

    assert outcome == "ok" and len(seen) == 3


def test_a_failing_sampler_never_breaks_the_battery():
    def broken():
        raise RuntimeError("nvidia-smi travou")

    outcome = cmp.run_guarded(["x"], {}, ".", 1000, memory=lambda: 8000, popen=lambda *a, **k: FakeProcess(2),
                              clock=lambda: 0, poll=1, sampler=broken)

    assert outcome == "ok"


def test_run_one_records_the_consumption_next_to_the_results(tmp_path, monkeypatch):
    monkeypatch.setattr(cmp, "sample_resources", lambda cpu=None: {"hora": "10:00:00", "ram_livre_mb": 4000, "vram_usada_mb": 6500.0})

    def fake_guarded(command, env, cwd, timeout, sampler=None, **kwargs):
        sampler()
        sampler()
        return "ok"

    monkeypatch.setattr(cmp, "run_guarded", fake_guarded)
    monkeypatch.setattr(cmp, "stop_model", lambda model, url=cmp.DEFAULT_URL: None)
    monkeypatch.setattr(cmp, "wait_unloaded", lambda model, seconds=40, url=cmp.DEFAULT_URL: True)

    cmp.run_one(cmp.profile_from_model("m"), tmp_path, SimpleNamespace(repeticoes=1, rapido=False, limite_modelo=5))

    assert cmp.summarize_consumption(tmp_path / cmp.CONSUMPTION_FILE)["amostras"] == 2


def result():
    return {"id": "a", "passed": True, "group": "simples", "info": False, "tok_s": 50.0, "seconds": 1.0, "tools": 1,
            "failed_tools": 0, "events": {}, "violations": [], "status": "completed", "attempt": 1, "detail": ""}


def test_collect_attaches_the_consumption_and_the_report_shows_it(tmp_path):
    (tmp_path / "resultados.json").write_text(json.dumps([result()]), encoding="utf-8")
    write_samples(tmp_path / cmp.CONSUMPTION_FILE, [
        {"hora": "1", "ram_livre_mb": 900, "vram_usada_mb": 7800.0, "vram_total_mb": 8192.0, "gpu_pct": 100.0, "potencia_w": 150.0, "temp_c": 78.0, "cpu_pct": 20.0},
    ])

    entry = cmp.collect(tmp_path, "9b")
    report = cmp.build_comparison([entry], "01/01/2027")

    assert entry["consumption"]["vram_pico_mb"] == 7800.0
    assert "## Consumo da máquina" in report
    assert "| 9b | 1 | 7800.0 de 8192 | 100.0 / 100.0 | 150.0 | 78.0 | 900.0 | 20.0 |" in report


def test_a_profile_without_consumption_data_simply_has_no_section(tmp_path):
    (tmp_path / "resultados.json").write_text(json.dumps([result()]), encoding="utf-8")

    entry = cmp.collect(tmp_path, "9b")

    assert "consumption" not in entry and "## Consumo da máquina" not in cmp.build_comparison([entry], "01/01/2027")
