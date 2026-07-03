import asyncio
from silex.core.tree_search import LanguageAgentTreeSearch

class MockLoop:
    pass

async def main():
    loop = MockLoop()
    import unittest.mock
    loop.llm = unittest.mock.AsyncMock()
    mock_cog = unittest.mock.MagicMock()
    mock_cog.reasoning = "Mock reasoning"
    mock_cog.response = "Mock response"
    mock_cog.tool_calls = []
    loop.llm.think.return_value = mock_cog

    loop.critic = unittest.mock.AsyncMock()
    mock_crit = unittest.mock.MagicMock()
    mock_crit.scores.accuracy = 0.9
    mock_crit.scores.depth = 0.9
    mock_crit.scores.honesty = 0.9
    mock_crit.is_acceptable = False
    mock_crit.feedback = "Mock feedback"
    loop.critic.critique.return_value = mock_crit
    loop.critic.geometric_score = lambda a, b, c: (a*b*c)**(1/3)
    loop._execute_tools = unittest.mock.AsyncMock(return_value=("Mock observation", False, [], []))
    
    loop.memory = unittest.mock.AsyncMock()
    mock_mem = unittest.mock.MagicMock()
    mock_mem.content = "mock mem"
    loop.memory.retrieve_context.return_value = [mock_mem]

    loop.session = unittest.mock.MagicMock()
    loop.causal_kg = unittest.mock.AsyncMock()

    lats = LanguageAgentTreeSearch(loop, max_iterations=1, exploration_constant=1.0, critic_threshold=0.95)
    
    print("[CHAOS TEST] Triggering LATS...")
    try:
        res = await lats.search("Test input", "System prompt")
        print("[CHAOS TEST] LATS completed successfully.")
        print(res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CHAOS TEST] LATS FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())
