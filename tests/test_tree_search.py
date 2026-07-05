import pytest
from unittest.mock import AsyncMock, MagicMock
from silex.core.tree_search import LATSNode, LanguageAgentTreeSearch
from silex.models.schemas import CognitiveResponse, CritiqueResponse, CritiqueScore


class FakeLLM:
    def __init__(self):
        self.connect = MagicMock()

    async def think(
        self,
        system_prompt,
        user_input,
        images=None,
        model_override=None,
        temperature=None,
    ):
        return CognitiveResponse(
            reasoning="Thinking...",
            response="Draft response from model",
            new_memories=[],
            goal_updates=[],
            self_reflection="Self-reflection...",
            confidence=0.9,
            tool_calls=[],
        )


@pytest.mark.asyncio
async def test_lats_node_ucb1():
    root = LATSNode(node_id="root", parent=None, critic_score=0.5, depth=0)
    child = LATSNode(node_id="child", parent=root, critic_score=0.8, depth=1)
    root.children.append(child)

    root.visit_count = 10
    root.value_sum = 5.0
    child.visit_count = 2
    child.value_sum = 1.6

    assert root.value == 0.5
    assert child.value == 0.8
    assert child.ucb1() > child.value


@pytest.mark.asyncio
async def test_lats_search_success():
    # Setup mock cognitive loop
    mock_loop = AsyncMock()
    mock_loop.llm = FakeLLM()

    # Mock MemoryStore
    mock_memory = AsyncMock()
    mock_memory.retrieve_context.return_value = []
    mock_loop.memory = mock_memory

    # Mock ResponseCritic
    mock_critic = AsyncMock()
    mock_critic.critique.return_value = CritiqueResponse(
        scores=CritiqueScore(accuracy=0.9, depth=0.9, honesty=0.9),
        is_acceptable=True,
        feedback="Excellent job!",
    )
    mock_critic.geometric_score = MagicMock(return_value=0.9)
    mock_loop.critic = mock_critic

    # Mock SessionManager
    mock_session = MagicMock()
    mock_session.current = MagicMock()
    mock_session.current.id = "session_123"
    mock_loop.session = mock_session

    # Mock CausalKnowledgeGraphGenerator
    mock_causal_kg = AsyncMock()
    mock_causal_kg.register_node.return_value = True
    mock_causal_kg.register_edge.return_value = True
    mock_loop.causal_kg = mock_causal_kg

    # Instantiate LATS
    lats = LanguageAgentTreeSearch(mock_loop, max_iterations=2)
    response = await lats.search(
        user_input="test query",
        system_prompt="system context",
    )

    assert isinstance(response, CognitiveResponse)
    assert response.confidence == 0.9
    assert response.response == "Draft response from model"
    assert mock_causal_kg.register_node.called
