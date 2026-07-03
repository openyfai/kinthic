import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from silex.core.cognitive_loop import CognitiveLoop
from silex.models.schemas import CognitiveResponse, MemoryType, NewMemory


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

    async def complete_json(self, *args, **kwargs):
        from silex.core.taste import TasteResponse, TasteScores
        return TasteResponse(
            scores=TasteScores(simplicity=1.0, performance=1.0, robustness=1.0, security=1.0),
            feedback="Tasteful design.",
            is_tasteful=True,
        )


class FakeCritic:
    async def critique(self, **kwargs):
        return SimpleNamespace(
            is_acceptable=True,
            scores=SimpleNamespace(accuracy=1.0, depth=1.0, honesty=1.0),
            feedback="Great work."
        )

    @staticmethod
    def geometric_score(accuracy: float, depth: float, honesty: float) -> float:
        return (accuracy * depth * honesty) ** (1.0 / 3.0)



def test_acquire_process_lock_cleans_up_stale_lock(tmp_path, monkeypatch, caplog):
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop._process_lock_path = tmp_path / ".aria-process.lock"
    loop._process_lock_path.write_text(json.dumps({"pid": 424242, "role": "old"}), encoding="utf-8")

    def fake_kill(pid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr("silex.core.cognitive_loop.allow_multi_writer", lambda: False)
    monkeypatch.setattr("silex.core.cognitive_loop.get_process_role", lambda: "test-role")
    monkeypatch.setattr("silex.core.cognitive_loop.os.kill", fake_kill)

    with caplog.at_level(logging.WARNING, logger="silex.core"):
        loop._acquire_process_lock()

    assert "stale process lock cleaned up" in caplog.text.lower()

    stored = json.loads(loop._process_lock_path.read_text(encoding="utf-8"))
    assert stored["pid"] == os.getpid()
    assert stored["role"] == "test-role"


def test_acquire_process_lock_raises_when_pid_is_alive(tmp_path, monkeypatch):
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop._process_lock_path = tmp_path / ".aria-process.lock"
    loop._process_lock_path.write_text(json.dumps({"pid": 424242, "role": "old"}), encoding="utf-8")

    monkeypatch.setattr("silex.core.cognitive_loop.allow_multi_writer", lambda: False)
    monkeypatch.setattr("silex.core.cognitive_loop.get_process_role", lambda: "test-role")
    monkeypatch.setattr("silex.core.cognitive_loop.os.kill", lambda pid, sig: None)

    with pytest.raises(RuntimeError, match="LOCK_EXISTS:424242"):
        loop._acquire_process_lock()


@pytest.mark.asyncio
async def test_cognitive_loop_happy_path_with_mocked_llm(tmp_path):
    with patch("silex.utils.config.SILEX_VECTOR_DB", tmp_path / "vector_db"):
        loop = CognitiveLoop()
        loop.db.db_path = str(tmp_path / "vyn.db")
        loop.llm = FakeGemini()
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
async def test_store_memories_marks_normative_and_character_provenance():
    """Verify _store_memories correctly sets provenance metadata.

    This test mocks the MemoryStore directly — it is testing the provenance
    logic inside _store_memories, NOT ChromaDB integration.
    """
    loop = CognitiveLoop.__new__(CognitiveLoop)

    stored_memories: list = []

    async def fake_add(memory):
        stored_memories.append(memory)
        return memory

    async def fake_all():
        return stored_memories

    loop.memory = SimpleNamespace(add=fake_add, all_memories=fake_all)
    loop.session = SimpleNamespace(current=SimpleNamespace(id="test-session", turn_count=0))

    count, _ = await loop._store_memories([
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

    normative = next(m for m in stored if m.memory_type == MemoryType.NORMATIVE)
    character = next(m for m in stored if m.memory_type == MemoryType.CHARACTER)

    assert normative.provenance["identity_relevant"] is True
    assert normative.provenance["requires_review"] is True
    assert normative.provenance["memory_type"] == "normative"

    assert character.provenance["identity_relevant"] is True
    assert character.provenance["requires_review"] is False
    assert character.provenance["memory_type"] == "character"


@pytest.mark.asyncio
async def test_resolve_hypothesis_manual_confirm(tmp_path):
    from silex.models.schemas import Hypothesis as HypothesisOut

    with patch("silex.utils.config.SILEX_VECTOR_DB", tmp_path / "vector_db"):
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


@pytest.mark.asyncio
async def test_background_memory_extraction_pipeline(tmp_path):
    """Verify that Fast Chat path enforces length gate, concurrency locks, and transaction routing in background memory extraction."""
    from silex.models.schemas import NewMemory as TestNewMemory, CausalObservation as TestCausalObservation
    from silex.core.cognitive_loop import ChatMemoryExtraction
    from unittest.mock import AsyncMock, patch, MagicMock

    with patch("silex.utils.config.SILEX_VECTOR_DB", tmp_path / "vector_db"), \
         patch("silex.memory.vector_store.SILEX_VECTOR_DB", tmp_path / "vector_db"):
        loop = CognitiveLoop()
        loop.db.db_path = str(tmp_path / "vyn.db")
        
        # Mocks
        loop.llm = MagicMock()
        
        # Mock complete_json to return an extraction payload
        mock_extracted = ChatMemoryExtraction(
            new_memories=[
                TestNewMemory(
                    content="VYN is a cognitive desktop agent.",
                    source="inference",
                    memory_type="semantic",
                    importance="situational",
                    tags=["system_info"],
                    confidence=0.9
                )
            ],
            causal_observations=[
                TestCausalObservation(
                    from_concept="user input",
                    to_concept="background task",
                    relationship="enables",
                    evidence="runs asynchronously",
                    strength=0.8
                )
            ]
        )
        
        loop.llm.complete_json = AsyncMock(return_value=mock_extracted)
        
        await loop.db.connect()
        await loop.kg.load()
        await loop.session.start_session()
        
        try:
            # 1. Length Gate Check (< 15 chars should bypass background task entirely)
            loop._is_extracting_memory = False
            
            with patch.object(loop, "_extract_chat_memory_async") as mock_extract:
                # Fast Chat trigger (must return CHAT in intent routing, mock this or call directly)
                loop.llm.think = AsyncMock()
                # Fast intent return
                mock_intent_resp = MagicMock()
                mock_intent_resp.response = "CHAT"
                
                mock_chat_resp = MagicMock()
                mock_chat_resp.response = "Hello!"
                
                loop.llm.think.side_effect = [mock_intent_resp, mock_chat_resp, mock_intent_resp, mock_chat_resp]
                
                # Short input
                await loop.process("hi")
                mock_extract.assert_not_called()
                
                # Long input (> 15 chars)
                await loop.process("hello cognitive agent world")
                mock_extract.assert_called_once()
                
            # 2. Concurrency Lock Check
            loop._is_extracting_memory = False
            
            # Let's test the actual async extraction helper
            with patch.object(loop.db, "transaction", wraps=loop.db.transaction) as mock_tx:
                # Run the background extraction
                await loop._extract_chat_memory_async(
                    user_input="hello cognitive agent world",
                    response_content="Hello!",
                    session_id=loop.session.current.id
                )
                
                # Verify lock was released
                assert loop._is_extracting_memory is False
                
                # Verify database writes were wrapped in a single, safe transaction!
                mock_tx.assert_called_once()
                
                # Verify the memory was saved
                await loop.memory.flush()
                mems = await loop.memory.all_memories()
                assert len(mems) == 1
                assert mems[0].content == "VYN is a cognitive desktop agent."
                
                # Verify graph nodes and edges were added
                nodes = await loop.db.fetch_all("SELECT * FROM knowledge_nodes")
                assert len(nodes) >= 2
                node_contents = [n["content"] for n in nodes]
                assert "user input" in node_contents
                assert "background task" in node_contents
                
                edges = await loop.db.fetch_all("SELECT * FROM causal_edges")
                assert len(edges) >= 1
        finally:
            await loop.shutdown()

