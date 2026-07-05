"""End-to-end recall track via the MCP service layer (production path)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from benchmarks.memory_recall.harness import (
    NeedleResult,
    _aggregate_needles,
    _score_needle,
)
from silex.mcp.server.lifecycle import create_standalone_context
from silex.mcp.server.schemas import RecallRequest
from silex.mcp.server import service as svc
from silex.models.schemas import Memory


async def run_mcp_e2e_condition(
    suite: dict[str, Any],
    condition: dict[str, Any],
    *,
    bench_dir: Path,
) -> dict[str, Any]:
    """Query a pre-seeded store via silex_recall MCP service."""
    import os

    import silex.memory.vector_store as vs_mod
    import silex.utils.config as cfg

    db_path = bench_dir / f"bench_{condition['name']}.db"
    bench_home = bench_dir / f"home_{condition['name']}"
    os.environ["KINTHIC_HOME"] = str(bench_home)
    os.environ["SILEX_DB"] = str(db_path)
    cfg.KINTHIC_HOME = bench_home
    cfg.SILEX_DB = db_path
    cfg.SILEX_VECTOR_DB = bench_home / "storage" / "vector_db"
    vs_mod.SILEX_VECTOR_DB = cfg.SILEX_VECTOR_DB

    ctx = await create_standalone_context(str(db_path))
    try:
        k_values = suite.get("scoring", {}).get("k_values", [5, 12])
        needle_results: list[NeedleResult] = []
        for needle in suite["needles"]:
            t0 = time.perf_counter()
            raw = await svc.recall(
                ctx, RecallRequest(query=needle["query"], limit=max(k_values))
            )
            elapsed = (time.perf_counter() - t0) * 1000
            data = json.loads(raw)
            memories = [
                Memory(id=m.get("memory_id", ""), content=m.get("content", ""))
                for m in data.get("memories", [])
            ]
            nr = _score_needle(memories, needle, k_values)
            nr.latency_ms = round(elapsed, 2)
            needle_results.append(nr)
        return _aggregate_needles(needle_results, k_values)
    finally:
        await ctx.memory.db.close()
