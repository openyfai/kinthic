"""Context flag for MCP HTTP tool writes (threaded SQLite path)."""

from __future__ import annotations

import contextvars

mcp_http_write_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "mcp_http_write", default=False
)
