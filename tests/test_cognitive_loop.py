import json
import logging
import os
from types import SimpleNamespace

import pytest

from aria.core.cognitive_loop import CognitiveLoop
from aria.models.schemas import CognitiveResponse, MemoryType, NewMemory


class FakeGemini:
    def connect(self):
        return None

    async def think(self, *args, **kwargs):
        return CognitiveResponse(
            reasoning="Used the available project context.",
            response="Done.",
            new_memories=[],
            goal_updates=[],
            self_reflection="No issues.",
            confidence=0.8,
            uncertainty_flags=[],
            uncertainty_tracking=[],
            causal_observations=[],
            contradictions_detected=[],
            hypotheses=[],
            hypothesis_resolutions=[],
            tool_calls=[],
        )


class FakeCritic:
    async def critique(self, **kwargs):
        return SimpleNamespace(is_acceptable=True)


def test_acquire_process_lock_cleans_up_stale_lock(tmp_path, monkeypatch, caplog):
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop._process_lock_path = tmp_path / ".aria-process.lock"
    loop._process_lock_path.write_text(json.dumps({"pid": 424242, "role": "old"}), encoding="utf-8")

    def fake_kill(pid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr("aria.core.cognitive_loop.allow_multi_writer", lambda: False)
    monkeypatch.setattr("aria.core.cognitive_loop.get_process_role", lambda: "test-role")
    monkeypatch.setattr("aria.core.cognitive_loop.os.kill", fake_kill)

    with caplog.at_level(logging.WARNING, logger="aria.core"):
        loop._acquire_process_lock()

    assert "You are VYN." in caplog.text
    assert "stale process lock cleaned up" in caplog.text.lower()

    stored = json.loads(loop._process_lock_path.read_text(encoding="utf-8"))
    assert stored["pid"] == os.getpid()
    assert stored["role"] == "test-role"


def test_acquire_process_lock_raises_when_pid_is_alive(tmp_path, monkeypatch):
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop._process_lock_path = tmp_path / ".aria-process.lock"
    loop._process_lock_path.write_text(json.dumps({"pid": 424242, "role": "old"}), encoding="utf-8")

    monkeypatch.setattr("aria.core.cognitive_loop.allow_multi_writer", lambda: False)
    monkeypatch.setattr("aria.core.cognitive_loop.get_process_role", lambda: "test-role")
    monkeypatch.setattr("aria.core.cognitive_loop.os.kill", lambda pid, sig: None)

    with pytest.raises(RuntimeError, match="LOCK_EXISTS:424242"):
        loop._acquire_process_lock()


@pytest.mark.asyncio
async def test_cognitive_loop_happy_path_with_mocked_llm(tmp_path):
    loop = CognitiveLoop()
    loop.db.db_path = str(tmp_path / "vyn.db")
    loop.gemini = FakeGemini()
    loop.critic = FakeCritic()
    loop.context_builder.pruner = None
    loop.context_builder.generalization_engine = None
    loop.context_builder.tool_registry = None

    await loop.db.connect()
    await loop.kg.load()
    await loop.session.start_session()

    try:
        response = await loop.process("Say done.")
        assert response.response == "Done."
        assert loop.session.current.turn_count == 1
    finally:
        await loop.shutdown()


@pytest.mark.asyncio
async def test_store_memories_marks_normative_and_character_provenance(tmp_path):
    loop = CognitiveLoop()
    loop.db.db_path = str(tmp_path / "vyn.db")

    await loop.db.connect()
    await loop.session.start_session()

    try:
        count = await loop._store_memories([
            NewMemory(
                content="ARIA must seek consent before high-impact actions.",
                source="system",
                memory_type="normative",
                importance="core",
                tags=["constitution"],
                confidence=0.9,
            ),
            NewMemory(
                content="ARIA chose honesty over convenience in a difficult turn.",
                source="reflection",
                memory_type="character",
                importance="core",
                tags=["formative"],
                confidence=0.75,
            ),
        ])

        stored = await loop.memory.all_memories()

        assert count == 2
        assert len(stored) == 2

        normative = next(memory for memory in stored if memory.memory_type == MemoryType.NORMATIVE)
        character = next(memory for memory in stored if memory.memory_type == MemoryType.CHARACTER)

        assert normative.provenance["identity_relevant"] is True
        assert normative.provenance["requires_review"] is True
        assert normative.provenance["memory_type"] == "normative"

        assert character.provenance["identity_relevant"] is True
        assert character.provenance["requires_review"] is False
        assert character.provenance["memory_type"] == "character"
    finally:
        await loop.shutdown()


@pytest.mark.asyncio
async def test_resolve_hypothesis_manual_confirm(tmp_path):
    from aria.models.schemas import Hypothesis as HypothesisOut

    loop = CognitiveLoop()
    loop.db.db_path = str(tmp_path / "vyn.db")

    await loop.db.connect()
    await loop.kg.load()
    await loop.session.start_session()

    try:
        h = await loop.hypotheses.store_hypothesis(
            HypothesisOut(claim="The sky is green on Tuesdays.", reasoning="Test.")
        )
        assert h.status == "pending"

        ok = await loop.resolve_hypothesis(h.id, "confirm")
        assert ok is True

        row = await loop.hypotheses.get_by_id(h.id)
        assert row is not None
        assert row.status == "confirmed"

        ok2 = await loop.resolve_hypothesis(h.id, "deny")
        assert ok2 is False
    finally:
        await loop.shutdown()
