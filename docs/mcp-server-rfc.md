# Silex Memory MCP Server — RFC

Status: **Implemented** (see `silex/mcp/server/`)

## Purpose

Expose the Silex memory engine as a [Model Context Protocol](https://modelcontextprotocol.io) server so external agents (Claude Desktop, Cursor, OpenClaw, Hermes) can recall and write persistent memory without running the full Kinthic cognitive loop.

## Architecture

- **In-process** on the Kinthic gateway (`/mcp` Streamable HTTP) sharing `MemoryStore` + `KnowledgeGraph` with `CognitiveLoop`.
- **stdio bridge** (`kinthic mcp serve --stdio`) proxies to the gateway when the daemon is running.
- **Standalone stdio** bootstraps an isolated `MemoryStore` when the daemon is stopped (onboarding demos only).

## Tool surface

| Tool | Write? | Backend | Notes |
|------|--------|---------|-------|
| `silex_recall` | No | `retrieve_context()` | Primary hybrid RRF recall |
| `silex_search` | No | `search()` | Keyword FTS |
| `silex_remember` | Yes | `add_with_result()` | Full A-MAC; returns admission metadata |
| `silex_remember_explicit` | Yes | `add_manual()` | User/agent facts; guard only |
| `silex_forget` | Yes | `delete()` | Requires `confirm=true` |
| `silex_get_memory` | No | `get()` | By UUID |
| `silex_list_memories` | No | paginated `all_memories()` | Optional tag filter |
| `silex_graph_recall` | No | `KnowledgeGraph.retrieve_relevant_context()` | Differentiator |
| `silex_memory_health` | No | stats + drift | Doctor integration |

### Intentional omissions (vs Mem0 MCP)

- `delete_all_memories` — too destructive; use CLI `kinthic data` with `--apply`
- `list_entities` / cloud scopes — local-first single-user; use `KINTHIC_MCP_CLIENT_ID` tag prefix instead
- Chat/completion tools — hosts bring their own LLM

## Admission response format

All write tools return structured admission metadata:

```json
{
  "admission": {
    "accepted": false,
    "reason": "amac_rejected",
    "amac_score": 0.42
  },
  "memory": null
}
```

Reasons: `duplicate`, `guard_blocked`, `amac_rejected`, `accepted`, `explicit`.

## Error codes

See `McpErrorCode` in [`silex/mcp/server/schemas.py`](../silex/mcp/server/schemas.py).

## Security

- HTTP `/mcp`: `x-kinthic-api-key` or `Authorization: Bearer <key>` (same as gateway)
- Loopback bind by default (`127.0.0.1`)
- Rate limits per tool (see `audit.py`)
- NDJSON audit log: `~/.kinthic/logs/mcp-audit.ndjson`
- HMAC key never passed to stdio child processes

## Transport

1. **Streamable HTTP** at `http://127.0.0.1:8000/mcp` (production)
2. **stdio bridge** for Claude Desktop / Cursor
3. **OAuth 2.1** — Phase 5 (`silex/mcp/server/oauth.py` stub)

## Client config

```bash
kinthic mcp print-config --client claude
```

```json
{
  "mcpServers": {
    "kinthic-memory": {
      "command": "kinthic",
      "args": ["mcp", "serve", "--stdio"]
    }
  }
}
```
