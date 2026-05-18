import json
import pytest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

from aria.core.cognitive_loop import CognitiveLoop
from aria.models.schemas import CognitiveResponse, ToolCall, ToolResult
from aria.utils.config import WORKSPACE_DIR

class FakeCritic:
    async def critique(self, **kwargs):
        return SimpleNamespace(
            is_acceptable=True,
            scores=SimpleNamespace(accuracy=1.0, depth=1.0, honesty=1.0)
        )

class FakeToolUsingGemini:
    def __init__(self):
        self.call_count = 0

    def connect(self):
        return None

    async def think(self, system_prompt, user_input, **kwargs):
        if "Fast Intent Router" in system_prompt:
            return CognitiveResponse(
                reasoning="Route to reasoning path.",
                response="REASON",
                new_memories=[],
                goal_updates=[],
                self_reflection="No issues.",
                confidence=1.0,
                uncertainty_flags=[],
                uncertainty_tracking=[],
                causal_observations=[],
                contradictions_detected=[],
                hypotheses=[],
                hypothesis_resolutions=[],
                tool_calls=[],
            )

        self.call_count += 1
        if self.call_count == 1:
            # Pass 1: Propose a tool call
            return CognitiveResponse(
                reasoning="I need to use search to find the latest version info.",
                response="Let me check search.",
                new_memories=[],
                goal_updates=[],
                self_reflection="No issues.",
                confidence=0.9,
                uncertainty_flags=[],
                uncertainty_tracking=[],
                causal_observations=[],
                contradictions_detected=[],
                hypotheses=[],
                hypothesis_resolutions=[],
                tool_calls=[
                    ToolCall(
                        tool_name="web_search",
                        arguments=json.dumps({"query": "latest OpenYF version"}),
                        expected_outcome="Information about OpenYF latest version.",
                        rationale="Find the latest version info."
                    )
                ],
                working_scratchpad="Need to search for latest OpenYF version."
            )
        else:
            # Pass 2: Final response incorporating tool results
            return CognitiveResponse(
                reasoning="Based on the search results, the latest version is 1.2.1.",
                response="The latest version is 1.2.1.",
                new_memories=[],
                goal_updates=[],
                self_reflection="No issues.",
                confidence=0.95,
                uncertainty_flags=[],
                uncertainty_tracking=[],
                causal_observations=[],
                contradictions_detected=[],
                hypotheses=[],
                hypothesis_resolutions=[],
                tool_calls=[],
                working_scratchpad="Search finished. Returning 1.2.1."
            )

@pytest.mark.asyncio
async def test_agentic_eval_harness_simulation(tmp_path):
    # Setup isolated environment
    db_path = tmp_path / "vyn_eval.db"
    vector_path = tmp_path / "vector_db"
    traces_file = WORKSPACE_DIR / "telemetry_traces.jsonl"
    
    # Clean previous traces if any to avoid bleed
    if traces_file.exists():
        try:
            traces_file.unlink()
        except Exception:
            pass

    with patch("aria.utils.config.VYN_VECTOR_DB", vector_path):
        loop = CognitiveLoop()
        loop.db.db_path = str(db_path)
        loop.gemini = FakeToolUsingGemini()
        loop.critic = FakeCritic()
        
        # De-active chroma and complex components for fast test run
        loop.context_builder.pruner = None
        loop.context_builder.generalization_engine = None
        loop.context_builder.tool_registry = None

        # Setup mock tool execution output
        mock_execute = AsyncMock(return_value=ToolResult(
            tool_name="web_search",
            actual_outcome="Version 1.2.1 is available.",
            success=True
        ))
        loop.tool_registry.execute = mock_execute

        # Connect and initialize session
        await loop.db.connect()
        await loop.kg.load()
        await loop.session.start_session()

        try:
            # Run the cognitive process
            response = await loop.process("Check the latest OpenYF version info.")
            
            # Assertions on cognitive loop response
            assert response.response == "The latest version is 1.2.1."
            assert loop.session.current.turn_count == 1

            # Assert tool execution was invoked correctly
            mock_execute.assert_called_once()
            
            # Verify database states:
            # 1. Turn registered in turns table
            turn_rows = await loop.db.fetch_all("SELECT * FROM turns WHERE session_id = ?", (loop.session.current.id,))
            assert len(turn_rows) == 1
            assert turn_rows[0]["response"] == "The latest version is 1.2.1."
            
            # 2. Checkpoints are successfully cleaned up/deleted
            checkpoint_rows = await loop.db.fetch_all("SELECT * FROM turn_checkpoints WHERE session_id = ?", (loop.session.current.id,))
            assert len(checkpoint_rows) == 0

            # 3. Telemetry traces were properly generated in JSONL
            assert traces_file.exists()
            with open(traces_file, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f]
                
            span_names = [span["name"] for span in lines]
            assert "build_context" in span_names
            assert "llm_pass_1" in span_names
            assert "tool_execution" in span_names
            assert "critic_evaluation" in span_names

        finally:
            await loop.shutdown()
