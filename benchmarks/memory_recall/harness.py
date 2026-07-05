#!/usr/bin/env python3
"""
Needle-in-haystack memory recall benchmark harness.

Measures Hit@k, MRR, and latency for Silex retrieval baselines under noise and age.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from benchmarks.memory_recall.noise_generator import generate_noise_memories
from silex.memory.memory_store import MemoryStore, _run_sync
from silex.models.schemas import Memory, MemorySource, MemoryType
from silex.storage.database import Database

RetrievalMode = Literal["none", "keyword", "vector", "hybrid"]
BASELINE_MODES: list[RetrievalMode] = ["none", "keyword", "vector", "hybrid"]
SUITE_PATH = Path(__file__).parent / "suite.yaml"
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class NeedleResult:
    needle_id: str
    query: str
    hit_at: dict[str, bool] = field(default_factory=dict)
    rank: int | None = None
    mrr: float = 0.0
    false_positive_top1: bool = False
    latency_ms: float = 0.0


@dataclass
class ConditionResult:
    name: str
    baselines: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_suite(path: Path | None = None) -> dict[str, Any]:
    with open(path or SUITE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _needle_token(content: str) -> str:
    return content.split()[0]


def _matches_needle(memory: Memory, needle: dict[str, Any]) -> bool:
    content = memory.content
    token = _needle_token(needle["content"])
    if token not in content:
        return False
    lower = content.lower()
    return all(fragment.lower() in lower for fragment in needle["must_contain"])


def _top_k(memories: list[Memory], k: int) -> list[Memory]:
    return memories[:k]


async def retrieve(
    store: MemoryStore,
    query: str,
    mode: RetrievalMode,
    *,
    limit: int = 12,
) -> list[Memory]:
    if mode == "none":
        return []
    if mode == "keyword":
        return await store._search_relevant(query, limit)
    if mode == "vector":
        return await _retrieve_vector_only(store, query, limit)
    results = await store.retrieve_context(query)
    return _top_k(results, limit)


async def _retrieve_vector_only(store: MemoryStore, query: str, limit: int) -> list[Memory]:
    if not store.vs.is_active or not query.strip():
        return []
    semantic_results = await _run_sync(store.vs.search, query, limit)
    if not semantic_results:
        return []
    semantic_ids = [res["id"] for res in semantic_results if res.get("id")]
    if not semantic_ids:
        return []
    placeholders = ",".join("?" * len(semantic_ids))
    rows = await store.db.fetch_all(
        f"SELECT * FROM memories WHERE id IN ({placeholders}) AND archived_at IS NULL",
        tuple(semantic_ids),
    )
    row_map = {row["id"]: row for row in rows}
    ordered: list[Memory] = []
    for res in semantic_results:
        row = row_map.get(res["id"])
        if row is None:
            continue
        mem = store._row_to_memory(row)
        if mem is not None:
            ordered.append(mem)
    return ordered[:limit]


async def _bulk_insert_memories(store: MemoryStore, memories: list[Memory]) -> None:
    """Insert memories into SQLite, FTS, and vector index."""
    if not memories:
        return

    rows = []
    fts_rows = []
    vector_texts: list[str] = []
    vector_metas: list[dict] = []
    vector_ids: list[str] = []

    fts_available = await store.fts5_available()

    for mem in memories:
        rows.append(
            (
                mem.id,
                mem.content,
                mem.source.value if hasattr(mem.source, "value") else mem.source,
                mem.memory_type.value if hasattr(mem.memory_type, "value") else mem.memory_type,
                mem.importance,
                mem.confidence,
                mem.created_at,
                mem.last_accessed,
                mem.access_count,
                json.dumps(mem.tags),
                mem.level,
                json.dumps(mem.child_memory_ids),
                json.dumps(mem.provenance),
                json.dumps(mem.related_memories),
                mem.archived_at,
                None,
            )
        )
        if fts_available:
            fts_rows.append((mem.content, mem.id))
        vector_texts.append(mem.content)
        vector_metas.append(
            {
                "type": mem.memory_type.value if hasattr(mem.memory_type, "value") else "semantic",
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
        vector_ids.append(mem.id)

    await store.db.executemany(
        """
        INSERT INTO memories (
            id, content, source, memory_type, importance, confidence,
            created_at, last_accessed, access_count, tags, level,
            child_memory_ids, provenance_json, related_memories, archived_at,
            content_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    if fts_available and fts_rows:
        await store.db.executemany(
            "INSERT INTO memories_fts(content, id) VALUES (?, ?)",
            fts_rows,
        )

    if store.vs.is_active:
        batch_size = 100
        for i in range(0, len(vector_texts), batch_size):
            await _run_sync(
                store.vs.add_chunks,
                vector_texts[i : i + batch_size],
                vector_metas[i : i + batch_size],
                vector_ids[i : i + batch_size],
            )


def _build_needle_memory(
    needle: dict[str, Any],
    *,
    age_days: float,
    importance: float,
) -> Memory:
    now = datetime.now(timezone.utc)
    ts = now - timedelta(days=age_days)
    iso = ts.isoformat()
    mem = Memory(
        id=str(uuid.uuid4()),
        content=needle["content"],
        source=MemorySource.USER,
        memory_type=MemoryType.SEMANTIC,
        importance=importance,
        confidence=0.9,
        tags=["benchmark_needle", f"needle:{needle['id']}"],
    )
    mem.created_at = iso
    mem.last_accessed = iso
    return mem


async def _seed_benchmark_store(
    store: MemoryStore,
    suite: dict[str, Any],
    *,
    seed: int,
    noise_count: int,
    condition: dict[str, Any],
) -> dict[str, str]:
    """Seed noise + needles; return needle_id -> memory uuid."""
    age_override = condition.get("age_days_override")
    importance_override = condition.get("importance_override")

    noise = generate_noise_memories(
        noise_count,
        suite["noise"]["templates"],
        seed=seed + hash(condition["name"]) % 10000,
        max_age_days=30,
    )
    await _bulk_insert_memories(store, noise)

    needle_ids: dict[str, str] = {}
    needle_memories: list[Memory] = []
    for needle in suite["needles"]:
        age_days = age_override if age_override is not None else needle.get("age_days", 0)
        importance = (
            importance_override
            if importance_override is not None
            else needle.get("importance", 0.5)
        )
        mem = _build_needle_memory(needle, age_days=float(age_days), importance=float(importance))
        needle_ids[needle["id"]] = mem.id
        needle_memories.append(mem)

    await _bulk_insert_memories(store, needle_memories)
    return needle_ids


def _score_needle(
    results: list[Memory],
    needle: dict[str, Any],
    k_values: list[int],
) -> NeedleResult:
    nr = NeedleResult(needle_id=needle["id"], query=needle["query"])
    rank: int | None = None
    for idx, mem in enumerate(results, 1):
        if _matches_needle(mem, needle):
            rank = idx
            break

    for k in k_values:
        nr.hit_at[str(k)] = rank is not None and rank <= k
    nr.rank = rank
    nr.mrr = (1.0 / rank) if rank else 0.0

    if results:
        top = results[0]
        top_matches = _matches_needle(top, needle)
        partial = all(fragment.lower() in top.content.lower() for fragment in needle["must_contain"])
        nr.false_positive_top1 = partial and not top_matches
    return nr


def _aggregate_needles(needles: list[NeedleResult], k_values: list[int]) -> dict[str, Any]:
    n = len(needles) or 1
    latencies = [n.latency_ms for n in needles]
    out: dict[str, Any] = {
        "queries": len(needles),
        "mrr": round(sum(n.mrr for n in needles) / n, 4),
        "false_positive_rate_top1": round(
            sum(1 for n in needles if n.false_positive_top1) / n, 4
        ),
        "latency_ms_p50": round(statistics.median(latencies), 2) if latencies else 0.0,
        "latency_ms_p95": round(
            sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2
        )
        if latencies
        else 0.0,
    }
    for k in k_values:
        key = f"hit_at_{k}"
        out[key] = round(
            sum(1 for n in needles if n.hit_at.get(str(k))) / n, 4
        )
    return out


async def run_condition(
    suite: dict[str, Any],
    condition: dict[str, Any],
    *,
    bench_dir: Path,
    seed: int,
    noise_count: int,
    modes: list[RetrievalMode],
) -> ConditionResult:
    import silex.memory.vector_store as vs_mod
    import silex.utils.config as cfg

    db_path = bench_dir / f"bench_{condition['name']}.db"
    bench_home = bench_dir / f"home_{condition['name']}"
    bench_home.mkdir(parents=True, exist_ok=True)
    vector_path = bench_home / "storage" / "vector_db"
    vector_path.mkdir(parents=True, exist_ok=True)

    os.environ["KINTHIC_HOME"] = str(bench_home)
    os.environ["SILEX_DB"] = str(db_path)
    cfg.KINTHIC_HOME = bench_home
    cfg.SILEX_DB = db_path
    cfg.SILEX_VECTOR_DB = vector_path
    vs_mod.SILEX_VECTOR_DB = vector_path

    db = Database(str(db_path))
    await db.connect()
    store = MemoryStore(db)

    try:
        await _seed_benchmark_store(
            store, suite, seed=seed, noise_count=noise_count, condition=condition
        )

        k_values = suite.get("scoring", {}).get("k_values", [5, 12])
        cr = ConditionResult(name=condition["name"])

        for mode in modes:
            needle_results: list[NeedleResult] = []
            async def _noop_bulk(_ids):  # noqa: ANN001
                return None

            store.update_access_bulk = _noop_bulk  # type: ignore[method-assign]
            for needle in suite["needles"]:
                t0 = time.perf_counter()
                results = await retrieve(store, needle["query"], mode, limit=max(k_values))
                elapsed = (time.perf_counter() - t0) * 1000
                nr = _score_needle(results, needle, k_values)
                nr.latency_ms = round(elapsed, 2)
                needle_results.append(nr)

            cr.baselines[mode] = _aggregate_needles(needle_results, k_values)
            cr.baselines[mode]["per_needle"] = [
                {
                    "id": n.needle_id,
                    "hit_at_5": n.hit_at.get("5", False),
                    "hit_at_12": n.hit_at.get("12", False),
                    "rank": n.rank,
                    "mrr": n.mrr,
                }
                for n in needle_results
            ]
        return cr
    finally:
        await db.close()


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Memory Recall Benchmark Report",
        "",
        f"- Suite version: {payload['suite_version']}",
        f"- Seed: {payload['seed']}",
        f"- Noise memories: {payload['noise_count']}",
        f"- Generated: {payload['generated_at']}",
        f"- Vector store active: {payload['vector_active']}",
        "",
    ]
    for condition in payload["conditions"]:
        lines.append(f"## Condition: `{condition['name']}`")
        lines.append("")
        lines.append(
            "| Baseline | Hit@5 | Hit@12 | MRR | p50 ms | p95 ms | FP@1 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for mode in BASELINE_MODES:
            if mode not in condition["baselines"]:
                continue
            b = condition["baselines"][mode]
            lines.append(
                f"| {mode} | {b.get('hit_at_5', 0):.2%} | {b.get('hit_at_12', 0):.2%} | "
                f"{b.get('mrr', 0):.3f} | {b.get('latency_ms_p50', 0):.1f} | "
                f"{b.get('latency_ms_p95', 0):.1f} | {b.get('false_positive_rate_top1', 0):.2%} |"
            )
        lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append(
        f"kinthic benchmark recall --seed {payload['seed']} --noise {payload['noise_count']}"
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


async def run_benchmark(
    *,
    seed: int = 42,
    noise_count: int | None = None,
    conditions: list[str] | None = None,
    output_json: Path | None = None,
    output_md: Path | None = None,
    bench_root: Path | None = None,
) -> dict[str, Any]:
    suite = load_suite()
    noise_count = noise_count if noise_count is not None else suite["noise"]["count"]
    selected = suite["conditions"]
    if conditions:
        names = set(conditions)
        selected = [c for c in suite["conditions"] if c["name"] in names]

    bench_dir = bench_root or Path(tempfile_mkdtemp())
    bench_dir.mkdir(parents=True, exist_ok=True)

    # Probe vector availability once
    try:
        import chromadb  # noqa: F401
        vector_active = True
    except ImportError:
        vector_active = False

    condition_results: list[ConditionResult] = []
    for condition in selected:
        condition_results.append(
            await run_condition(
                suite,
                condition,
                bench_dir=bench_dir,
                seed=seed,
                noise_count=noise_count,
                modes=BASELINE_MODES,
            )
        )

    payload: dict[str, Any] = {
        "benchmark": "memory_recall",
        "suite_version": suite.get("version", 1),
        "seed": seed,
        "noise_count": noise_count,
        "needle_count": len(suite["needles"]),
        "vector_active": vector_active,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conditions": [
            {"name": cr.name, "baselines": cr.baselines} for cr in condition_results
        ],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = output_json or RESULTS_DIR / "latest.json"
    md_path = output_md or RESULTS_DIR / "REPORT.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_report(payload), encoding="utf-8")

    return payload


def tempfile_mkdtemp() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="kinthic_recall_bench_")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kinthic memory recall benchmark")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise", type=int, default=None, help="Override noise memory count")
    parser.add_argument(
        "--conditions",
        nargs="*",
        default=None,
        help="Condition names to run (default: all)",
    )
    parser.add_argument("--output", type=Path, default=None, help="JSON output path")
    parser.add_argument("--report", type=Path, default=None, help="Markdown report path")
    parser.add_argument(
        "--track",
        choices=["retrieval", "mcp"],
        default="retrieval",
        help="retrieval=MemoryStore baselines (default); mcp=silex_recall service path",
    )
    args = parser.parse_args(argv)

    if args.track == "mcp":
        payload = asyncio.run(
            run_mcp_benchmark(
                seed=args.seed,
                noise_count=args.noise,
                conditions=args.conditions,
                output_json=args.output,
                output_md=args.report,
            )
        )
    else:
        payload = asyncio.run(
            run_benchmark(
                seed=args.seed,
                noise_count=args.noise,
                conditions=args.conditions,
                output_json=args.output,
                output_md=args.report,
            )
        )
    print(json.dumps(payload, indent=2))
    return 0


async def run_mcp_benchmark(
    *,
    seed: int = 42,
    noise_count: int | None = None,
    conditions: list[str] | None = None,
    output_json: Path | None = None,
    output_md: Path | None = None,
    bench_root: Path | None = None,
) -> dict[str, Any]:
    """Run MCP e2e track: seed via harness, score via silex_recall."""
    from benchmarks.memory_recall.e2e import run_mcp_e2e_condition

    suite = load_suite()
    noise_count = noise_count if noise_count is not None else suite["noise"]["count"]
    selected = suite["conditions"]
    if conditions:
        names = set(conditions)
        selected = [c for c in suite["conditions"] if c["name"] in names]

    bench_dir = bench_root or Path(tempfile_mkdtemp())
    bench_dir.mkdir(parents=True, exist_ok=True)

    condition_payloads = []
    for condition in selected:
        # Seed DB (none mode only — no queries yet)
        await run_condition(
            suite,
            condition,
            bench_dir=bench_dir,
            seed=seed,
            noise_count=noise_count,
            modes=["none"],
        )
        mcp_scores = await run_mcp_e2e_condition(
            suite,
            condition,
            bench_dir=bench_dir,
        )
        condition_payloads.append({"name": condition["name"], "baselines": {"mcp_recall": mcp_scores}})

    payload: dict[str, Any] = {
        "benchmark": "memory_recall_mcp",
        "suite_version": suite.get("version", 1),
        "seed": seed,
        "noise_count": noise_count,
        "track": "mcp",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conditions": condition_payloads,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = output_json or RESULTS_DIR / "mcp-e2e.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
