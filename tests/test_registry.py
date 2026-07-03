import json

import pytest

from silex.models.schemas import ToolCall
from silex.tools.base import BaseTool
from silex.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo test input."
    schema = {"text": "string"}

    async def execute(self, **kwargs) -> str:
        return f"Echo: {kwargs['text']}"


class NetworkTool(BaseTool):
    name = "network_probe"
    description = "Pretend network action."
    risk_level = "network"
    schema = {"url": "string"}

    async def execute(self, **kwargs) -> str:
        return f"Fetched: {kwargs['url']}"


class DestructiveTool(BaseTool):
    name = "destroy"
    description = "Pretend destructive action."
    risk_level = "destructive"
    schema = {"target": "string"}

    async def execute(self, **kwargs) -> str:
        return f"Destroyed: {kwargs['target']}"


@pytest.mark.asyncio
async def test_registry_strips_unexpected_args():
    registry = ToolRegistry()
    registry.tools = {}
    registry.register(EchoTool())

    result = await registry.execute(ToolCall(
        tool_name="echo",
        arguments=json.dumps({"text": "hello", "unexpected": "drop me"}),
        expected_outcome="echoes",
        rationale="exercise schema validation",
    ))

    assert result.success is True
    assert result.actual_outcome == "Echo: hello"


@pytest.mark.asyncio
async def test_registry_unknown_tool_fails():
    registry = ToolRegistry()
    registry.tools = {}

    result = await registry.execute(ToolCall(
        tool_name="missing",
        arguments=json.dumps({}),
        expected_outcome="nothing",
        rationale="exercise unknown tool path",
    ))

    assert result.success is False
    assert result.error == "Tool not found"


@pytest.mark.asyncio
async def test_registry_escalates_background_network_actions():
    registry = ToolRegistry()
    registry.tools = {}
    registry.register(NetworkTool())

    result = await registry.execute(
        ToolCall(
            tool_name="network_probe",
            arguments=json.dumps({"url": "https://example.com"}),
            expected_outcome="fetches a page",
            rationale="needs external information",
        ),
        execution_mode="background",
    )

    assert result.success is False
    assert result.error == "approval_required"
    assert result.ethical_decision is not None
    assert result.ethical_decision.action.value == "escalate"
    assert result.ethical_decision.principle == "corrigibility"


@pytest.mark.asyncio
async def test_semantic_search_omitted_when_vector_inactive():
    class InactiveVS:
        is_active = False

    registry = ToolRegistry(vector_store=InactiveVS())
    assert "semantic_search" not in registry.tools


@pytest.mark.asyncio
async def test_semantic_search_execute_explains_when_inactive():
    from silex.tools.search import SemanticSearchTool

    class InactiveVS:
        is_active = False

    tool = SemanticSearchTool(InactiveVS())
    msg = await tool.execute(query="anything")
    assert "disabled" in msg.lower()


@pytest.mark.asyncio
async def test_registry_refuses_destructive_actions():
    registry = ToolRegistry()
    registry.tools = {}
    registry.register(DestructiveTool())

    result = await registry.execute(
        ToolCall(
            tool_name="destroy",
            arguments=json.dumps({"target": "/tmp/data"}),
            expected_outcome="deletes data",
            rationale="cleanup",
        )
    )

    assert result.success is False
    assert result.error == "ethical_refusal"
    assert result.ethical_decision is not None
    assert result.ethical_decision.action.value == "refuse"
    assert result.ethical_decision.principle == "beneficence"
