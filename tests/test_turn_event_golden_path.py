"""Golden-path turn event sequence for operator UI trust."""

from __future__ import annotations

import json

import pytest

from silex.ui.turn_events import TurnPhase
from silex.ui.turn_emitter import TurnEmitter


@pytest.mark.asyncio
async def test_golden_path_turn_event_sequence() -> None:
    events: list[dict] = []

    async def capture(msg: dict) -> None:
        events.append(msg)

    emitter = TurnEmitter(capture, turn_id="turn_test_001", mirror_legacy=False)

    await emitter.user_message("spawn an agent to find Anthropic blog")
    await emitter.routing("[Fast Router] Routed to FAST path")
    await emitter.tool_start("spawn_worker", "1 tool call(s) planned")
    await emitter.approval_request(
        "appr-1",
        "spawn_worker",
        "sandbox_write",
        "Approval required for spawn_worker",
    )
    await emitter.approval_result("appr-1", "spawn_worker", "sandbox_write", True)
    await emitter.tool_progress("spawn_worker", "Running approved tool...")
    await emitter.subagent(
        "cw-001",
        "running",
        objective="Find latest Anthropic blog",
        worker_class="cognitive_worker",
    )
    await emitter.subagent(
        "cw-001",
        "done",
        objective="Find latest Anthropic blog",
        worker_class="cognitive_worker",
        detail="Found https://anthropic.com/research/example",
    )
    await emitter.assistant_done("Here is what the agent found: example post.")
    await emitter.memory(1, ["User asked about Anthropic blog"])
    await emitter.turn_summary(
        latency_ms=45200,
        tokens=12400,
        memories_written=1,
        tools_executed=1,
        workers_used=1,
    )

    turn_events = [e for e in events if e.get("type") == "turn_event"]
    assert len(turn_events) == 11

    turn_id = turn_events[0]["data"]["turn_id"]
    assert all(e["data"]["turn_id"] == turn_id for e in turn_events)

    seqs = [e["data"]["seq"] for e in turn_events]
    assert seqs == list(range(1, len(seqs) + 1))

    phases = [e["data"]["phase"] for e in turn_events]
    assert phases[0] == TurnPhase.USER.value
    assert "routing" in phases
    assert "tool" in phases
    assert phases.count("approval") == 2
    assert phases.count("subagent") == 2
    assert phases[-2] == TurnPhase.MEMORY.value
    assert phases[-1] == TurnPhase.SUMMARY.value


@pytest.mark.asyncio
async def test_turn_emitter_mirror_legacy_worker_and_approval(tmp_path, monkeypatch) -> None:
    from silex.ui import ink_bridge as ib

    kronos_dir = tmp_path / ".kronos"
    kronos_dir.mkdir()
    path = kronos_dir / "ink_events.ndjson"
    monkeypatch.setattr(ib, "_KRONOS_DIR", kronos_dir)
    monkeypatch.setattr(ib, "_EVENTS_FILE", path)

    bridge = ib.KronosInkBridge()
    bridge._enabled = True

    emitter = TurnEmitter(bridge.emit, turn_id="turn_mirror", mirror_legacy=True)
    await emitter.approval_request("a1", "spawn_worker", "sandbox_write", "needs approval")
    await emitter.subagent("w1", "running", objective="test", worker_class="cognitive_worker")

    lines = [json.loads(l) for l in path.read_text().strip().splitlines()]
    types = [l["type"] for l in lines]
    assert "turn_event" in types
    assert "approval_requested" in types
    assert "worker" in types
