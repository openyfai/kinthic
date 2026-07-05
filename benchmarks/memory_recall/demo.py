#!/usr/bin/env python3
"""Interactive memory recall demo for asciinema / website hero."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from silex.mcp.server.lifecycle import create_standalone_context
from silex.mcp.server.schemas import RecallRequest, RememberExplicitRequest
from silex.mcp.server import service as svc


async def demo() -> None:
    import silex.memory.vector_store as vs_mod
    import silex.utils.config as cfg

    bench = Path(tempfile.mkdtemp(prefix="kinthic_demo_"))
    db_path = bench / "demo.db"
    os.environ["KINTHIC_HOME"] = str(bench / "home")
    os.environ["SILEX_DB"] = str(db_path)
    cfg.KINTHIC_HOME = bench / "home"
    cfg.SILEX_DB = db_path
    cfg.SILEX_VECTOR_DB = bench / "home" / "storage" / "vector_db"
    cfg.SILEX_VECTOR_DB.mkdir(parents=True, exist_ok=True)
    vs_mod.SILEX_VECTOR_DB = cfg.SILEX_VECTOR_DB

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  Kinthic Memory Recall Demo                              ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    ctx = await create_standalone_context(str(db_path))
    try:
        fact = "Staging postgres URL is postgres://staging.internal:5432/kinthic"
        print(f"Turn 1 — store fact:\n  > {fact}\n")
        write = json.loads(
            await svc.remember_explicit(ctx, RememberExplicitRequest(content=fact))
        )
        print(f"  ✓ stored (admission: {write['admission']['reason']})\n")

        noise = [
            "Discussed dashboard refactor in standup.",
            "User prefers vim over vscode for editing.",
            "Debug log: api returned 502 at 14:32.",
            "Meeting summary: sprint planning action items.",
        ]
        print("Turns 2–5 — unrelated conversation noise …")
        for line in noise:
            await svc.remember_explicit(ctx, RememberExplicitRequest(content=line))
            time.sleep(0.15)
        print("  (4 distractor memories stored)\n")

        query = "What's the staging Postgres URL?"
        print(f"Turn 6 — recall without re-pasting the URL:\n  > {query}\n")
        t0 = time.perf_counter()
        recalled = json.loads(await svc.recall(ctx, RecallRequest(query=query, limit=5)))
        ms = (time.perf_counter() - t0) * 1000
        hits = [
            m["content"]
            for m in recalled.get("memories", [])
            if "postgres" in m.get("content", "").lower()
        ]
        if hits:
            print(f"  ✓ recalled in {ms:.0f}ms:\n    {hits[0]}\n")
        else:
            print("  ✗ no matching memory found\n")
            raise SystemExit(1)

        print("Benchmark headline (published v1, 500 noise, seed 42, aged 21d):")
        print("  Hybrid Hit@5: 67% | Hit@12: 92% (keyword-only Hit@5: 42%)")
        print("  Reproduce: kinthic benchmark recall\n")
    finally:
        await ctx.memory.db.close()


def main() -> int:
    asyncio.run(demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
