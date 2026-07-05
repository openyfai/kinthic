"""Tests for the memory recall benchmark harness."""

from __future__ import annotations

import pytest

from benchmarks.memory_recall.harness import load_suite, run_benchmark


@pytest.mark.asyncio
async def test_memory_recall_benchmark_ci_gate(tmp_path):
    """Fast CI gate: hybrid should beat keyword on aged noise with 50 distractors."""
    payload = await run_benchmark(
        seed=42,
        noise_count=50,
        conditions=["aged_21d"],
        output_json=tmp_path / "out.json",
        output_md=tmp_path / "REPORT.md",
        bench_root=tmp_path / "bench",
    )

    cond = next(c for c in payload["conditions"] if c["name"] == "aged_21d")
    hybrid = cond["baselines"]["hybrid"]
    keyword = cond["baselines"]["keyword"]
    none = cond["baselines"]["none"]

    assert none["hit_at_5"] == 0.0
    assert hybrid["hit_at_5"] >= 0.70
    assert hybrid["hit_at_12"] >= 0.85
    assert hybrid["hit_at_5"] >= keyword["hit_at_5"]
    assert hybrid["mrr"] >= keyword["mrr"]


def test_suite_loads_needles():
    suite = load_suite()
    assert suite["version"] == 1
    assert len(suite["needles"]) >= 8
    assert suite["noise"]["count"] == 500


@pytest.mark.asyncio
async def test_low_importance_condition_runs(tmp_path):
    payload = await run_benchmark(
        seed=7,
        noise_count=30,
        conditions=["aged_21d_low_importance"],
        output_json=tmp_path / "low.json",
        output_md=tmp_path / "low.md",
        bench_root=tmp_path / "bench2",
    )
    cond = next(c for c in payload["conditions"] if c["name"] == "aged_21d_low_importance")
    assert cond["baselines"]["hybrid"]["queries"] == len(load_suite()["needles"])


@pytest.mark.asyncio
async def test_mcp_e2e_track_matches_hybrid(tmp_path):
    from benchmarks.memory_recall.harness import run_mcp_benchmark

    payload = await run_mcp_benchmark(
        seed=42,
        noise_count=50,
        conditions=["aged_21d"],
        bench_root=tmp_path / "mcp_bench",
    )
    mcp = next(c for c in payload["conditions"] if c["name"] == "aged_21d")["baselines"]["mcp_recall"]
    assert mcp["hit_at_5"] >= 0.75
