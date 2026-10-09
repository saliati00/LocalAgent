"""Estimativa de memória e velocidade: classes de encaixe corretas e calibrada com o que foi medido."""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import estimar_desempenho as est  # noqa: E402

HW = dict(est.DEFAULT_HARDWARE)


def row(name, **kwargs):
    model = next(m for m in est.MODELS if m["name"] == name)
    return est.estimate(model, {**HW, **kwargs.pop("hw", {})}, **kwargs)


def test_small_dense_models_fit_entirely_in_the_gpu():
    for name in ("qwen3:8b", "qwen3.5:4b"):
        assert row(name)["fit"] == "100% GPU" and row(name)["cpu_pct"] == 0


def test_a_model_slightly_bigger_than_the_vram_spills_a_little_to_the_cpu():
    result = row("gemma4:12b")

    assert result["fit"].startswith("parcial") and 0 < result["cpu_pct"] < 30 and result["fits_ram"]


def test_the_biggest_moe_does_not_fit_the_memory_and_is_flagged_as_a_freeze_risk():
    result = row("qwen3-coder:30b")

    assert result["fit"].startswith("NÃO CABE") and result["freeze_risk"] is True
    assert "TRAVAR" in est.verdict(result)


def test_more_ram_makes_the_big_model_fit():
    assert row("qwen3-coder:30b", hw={"ram_gb": 32})["fits_ram"] is True


def test_quantized_kv_cache_halves_the_cache_and_moves_less_to_the_cpu():
    normal, quantized = row("gemma4:12b"), row("gemma4:12b", kv8=True)

    assert quantized["kv_gb"] == pytest.approx(normal["kv_gb"] / 2, abs=0.01)
    assert quantized["cpu_pct"] <= normal["cpu_pct"]


def test_a_bigger_context_grows_the_cache_linearly():
    assert row("qwen3:8b", ctx=16384)["kv_gb"] == pytest.approx(2 * row("qwen3:8b", ctx=8192)["kv_gb"], abs=0.01)


def test_cpu_offload_makes_generation_much_slower_than_pure_gpu():
    assert row("qwen3:8b")["tok_s"] > 3 * row("devstral:24b")["tok_s"]


def test_a_dense_24b_is_unusable_and_a_moe_with_few_active_params_is_usable():
    assert est.verdict(row("devstral:24b")).startswith("inviável")
    assert row("gpt-oss:20b")["tok_s"] > row("devstral:24b")["tok_s"] * 3


def test_paging_to_disk_is_far_slower_than_the_same_model_with_enough_ram():
    paged, comfortable = row("qwen3-coder:30b"), row("qwen3-coder:30b", hw={"ram_gb": 32})

    assert paged["tok_s"] < comfortable["tok_s"] / 3


def test_the_estimate_matches_the_models_measured_on_this_machine_within_15_percent():
    for name in ("qwen3:8b", "qwen3.5:4b", "qwen3.5:9b"):
        result = row(name)
        error = abs(result["tok_s"] - result["measured"]["tok_s"]) / result["measured"]["tok_s"]

        assert error < 0.15, f"{name}: erro de {error:.0%}"


def test_validation_admits_when_the_fit_was_wrong():
    notes = est.validation([row("qwen3:8b"), row("qwen3.5:9b")])

    assert "ERROU o encaixe" in notes[1] and "ERROU" not in notes[0]


def test_table_lists_every_model_and_the_cli_runs(capsys):
    assert est.main(["--kv8", "--ctx", "16384"]) == 0

    out = capsys.readouterr().out

    for model in est.MODELS:
        assert model["name"] in out

    assert "VALIDAÇÃO" in out and "cache KV em 8 bits" in out
