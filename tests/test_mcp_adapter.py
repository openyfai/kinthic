"""MCP adapter and config tests (no live npx servers)."""

import pytest

from silex.mcp.adapter import McpToolAdapter
from silex.mcp.config import McpConfig
from silex.mcp.presets import get_preset


@pytest.mark.asyncio
async def test_mcp_tool_adapter_execute():
    async def call_fn(tool_name, args):
        return f"called {tool_name} with {args}"

    tool = McpToolAdapter(
        server_name="test",
        tool_name="echo",
        description="Echo tool",
        input_schema={"type": "object"},
        call_fn=call_fn,
    )
    result = await tool.execute(message="hi")
    assert "echo" in result
    assert "hi" in result


def test_mcp_config_enabled_servers(tmp_path, monkeypatch):
    cfg_path = tmp_path / "mcp.yaml"
    cfg_path.write_text(
        "servers:\n  a:\n    enabled: true\n    command: echo\n  b:\n    enabled: false\n",
        encoding="utf-8",
    )
    cfg = McpConfig(cfg_path, {"servers": {"a": {"enabled": True}, "b": {"enabled": False}}})
    assert list(cfg.enabled_servers().keys()) == ["a"]


def test_filesystem_preset_has_workspace():
    preset = get_preset("filesystem")
    assert preset is not None
    assert preset["command"] == "npx"
    assert "server-filesystem" in preset["args"][1]


@pytest.mark.integration
@pytest.mark.skip(reason="Requires npx and @modelcontextprotocol/server-filesystem")
@pytest.mark.asyncio
async def test_live_filesystem_mcp():
    from silex.mcp.manager import get_mcp_manager
    from silex.mcp.config import write_server
    from silex.mcp.presets import get_preset

    preset = dict(get_preset("filesystem") or {})
    preset["enabled"] = True
    write_server("filesystem", preset)
    ok, msg = await get_mcp_manager().test_server("filesystem")
    assert ok, msg
