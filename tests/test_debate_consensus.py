import pytest
from unittest.mock import AsyncMock, MagicMock
from silex.core.debate import DebateEngine, ConsensusCritique, ConsensusDebateResponse

class FakeLLM:
    def __init__(self):
        self.call_count = 0

    async def complete_json(self, schema, system_prompt, user_input, temperature, request_kind):
        self.call_count += 1
        # SystemArchitect, StaffEngineer, SecurityAuditor
        # Return high scores on round 2 or if we mock consensus
        score = 0.95 if self.call_count > 3 else 0.7
        return ConsensusCritique(
            role="Expert",
            score=score,
            critique="Looks okay.",
            suggestions=["Make it more modular."]
        )

    async def think(self, system_prompt, user_input, temperature=None):
        return MagicMock(response="def new_code():\n    pass")

@pytest.mark.asyncio
async def test_run_consensus_debate():
    mock_db = AsyncMock()
    fake_llm = FakeLLM()
    engine = DebateEngine(llm_client=fake_llm, db=mock_db)

    response = await engine.run_consensus_debate(
        draft_code="def code(): pass",
        goal_description="Create a simple helper function"
    )

    assert isinstance(response, ConsensusDebateResponse)
    assert len(response.critiques) == 3
    # Check that consensus was achieved on round 2 (since FakeLLM returns score=0.95 after first round)
    assert response.consensus_achieved is True
    assert "def new_code():" in response.refined_code
