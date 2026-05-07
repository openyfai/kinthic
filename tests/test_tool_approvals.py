import json

import pytest

from aria.tools.base import BaseTool
from aria.tools.registry import ToolRegistry


class ApprovalTool(BaseTool):
    name = "approval_tool"
    description = "A tool that requires approval."
    risk_level = "repo_write"
    requires_approval = True
    schema = {"path": "string"}

    async def execute(self, **kwargs) -> str:
        return f"Updated {kwargs['path']}"


class FakeDB:
    def __init__(self):
        self.rows = {}

    async def execute(self, sql: str, params: tuple = ()):
        if "INSERT INTO tool_approvals" in sql:
            self.rows[params[0]] = {
                "id": params[0],
                "tool_name": params[2],
                "risk_level": params[3],
                "arguments_json": params[4],
                "expected_outcome": params[5],
                "reason": params[6],
                "status": params[7],
            }
        elif "UPDATE tool_approvals SET status" in sql:
            row = self.rows[params[3]]
            row["status"] = params[0]
            row["execution_result_json"] = params[2]
        return None

    async def fetch_one(self, sql: str, params: tuple = ()):
        return self.rows.get(params[0])

    async def fetch_all(self, sql: str, params: tuple = ()):
        return [row for row in self.rows.values() if row["status"] == "pending"]


@pytest.mark.asyncio
async def test_resolving_approval_executes_tool():
    registry = ToolRegistry()
    registry.tools = {}
    registry.register(ApprovalTool())
    registry.db = FakeDB()

    approval_id = await registry._queue_approval(
        registry.tools["approval_tool"],
        {"path": "demo.txt"},
        "Update demo file",
    )

    ok = await registry.resolve_approval(approval_id, "approved")

    assert ok is True
    stored = registry.db.rows[approval_id]
    result = json.loads(stored["execution_result_json"])
    assert stored["status"] == "approved"
    assert result["success"] is True
    assert "demo.txt" in result["actual_outcome"]
