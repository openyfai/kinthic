"""Silex memory MCP server — expose cognition to external agents."""

from silex.mcp.server.app import create_mcp_app, mount_mcp_server
from silex.mcp.server.lifecycle import McpServerContext, create_standalone_context

__all__ = [
    "McpServerContext",
    "create_mcp_app",
    "create_standalone_context",
    "mount_mcp_server",
]
