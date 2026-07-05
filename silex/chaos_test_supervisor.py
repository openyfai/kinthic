import asyncio
import sys
from silex.tools.base import BaseTool
from silex.models.schemas import ToolCall, EthicalAction
from silex.tools.registry import ToolRegistry


class HangingTool(BaseTool):
    name = "hanging_tool"
    description = "A tool that hangs infinitely to test the global supervisor."
    timeout_seconds = 1.5  # Short timeout for testing

    async def execute(self, **kwargs) -> str:
        print("   [HangingTool] Starting infinite loop. I will never yield...")
        await asyncio.sleep(9999)
        return "I finished!"


async def main():
    print("[CHAOS TEST] Triggering Infinite Tool Hang Simulation...")

    # Bypass ethics engine requirement for the test
    registry = ToolRegistry()
    registry.register(HangingTool())

    from silex.models.schemas import EthicalDecision
    import unittest.mock

    mock_decision = EthicalDecision(
        action=EthicalAction.PROCEED,
        principle="test",
        rationale="test",
        risk_level="read_only",
        requires_consent=False,
        uncertainty=0.0,
        context="test",
    )
    registry.ethics.evaluate_tool_call = unittest.mock.MagicMock(
        return_value=mock_decision
    )
    registry._log_ethical_decision = unittest.mock.AsyncMock()

    call = ToolCall(
        tool_name="hanging_tool",
        arguments="{}",
        expected_outcome="Nothing",
        rationale="For testing",
    )

    print("-> Firing HangingTool inside DAG Orchestrator...")
    try:
        # execute_with_gate calls execute() which has the timeout logic
        result = await registry.execute_with_gate(call, execution_mode="auto")
    except Exception as e:
        print(f"[CHAOS TEST] FAILED. Registry threw an unhandled exception: {e}")
        sys.exit(1)

    print(
        f"-> Registry returned result: success={result.success}, outcome='{result.actual_outcome}'"
    )

    if result.success:
        print("[CHAOS TEST] FAILED. The hanging tool incorrectly succeeded!")
        sys.exit(1)

    if "timed out" not in result.actual_outcome.lower():
        print(
            f"[CHAOS TEST] FAILED. The tool failed, but not because of a timeout. Outcome: {result.actual_outcome}"
        )
        sys.exit(1)

    print(
        "[CHAOS TEST] SUCCESS. The Global Execution Supervisor successfully detected the infinite hang, severed the thread, and returned a structured timeout failure without deadlocking the engine."
    )


if __name__ == "__main__":
    asyncio.run(main())
