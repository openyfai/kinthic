# MCP integration

Kinthic can connect to external **Model Context Protocol (MCP)** servers and expose their tools to the agent alongside built-in tools.

## Quick start

After `kinthic init`, enable a preset:

```bash
kinthic mcp add filesystem --preset filesystem
kinthic mcp enable filesystem
kinthic mcp test filesystem
```

Or during onboarding, choose **Enable filesystem MCP** when prompted.

## Configuration

Servers live in `~/.kinthic/config/mcp.yaml`:

```yaml
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/.kinthic/workspace"]
    enabled: true
    allowed_tools: ["read_file", "list_directory"]
    requires_approval: ["write_file"]
```

Secrets use environment variable expansion: `${GITHUB_PERSONAL_ACCESS_TOKEN}` — never commit tokens.

## CLI commands

| Command | Purpose |
|---------|---------|
| `kinthic mcp list` | Show configured servers |
| `kinthic mcp add <name> --preset filesystem` | Add from bundled preset |
| `kinthic mcp enable\|disable <name>` | Toggle a server |
| `kinthic mcp test <name>` | Verify connectivity |
| `kinthic mcp tools [--server <name>]` | List discovered tools |

## In-session commands

Inside `kinthic` TUI:

- `:mcp list`
- `:mcp enable <name>`
- `:mcp disable <name>`
- `:mcp reload`
- `:mcp test <name>`

## Security defaults

- MCP servers run as **separate processes** — the HMAC key is never passed to child env.
- Filesystem preset defaults to **workspace root only** (`WORKSPACE_DIR`).
- Tools listed under `requires_approval` go through the same approval gate as terminal commands.
- Run `kinthic doctor` to see enabled MCP servers and risky combinations.

## Install MCP support

The installer pulls the `[mcp]` extra automatically. From source:

```bash
pip install -e ".[mcp]"
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `MCP extra not installed` | `pip install -e ".[mcp]"` |
| `npx` not found | Install Node.js 18+ for filesystem/github presets |
| `uvx` not found | Install uv for fetch preset |
| Server test fails | Run `kinthic mcp test <name>` and check command/args in mcp.yaml |

## Custom servers

```bash
kinthic mcp add myserver --exec uvx --args mcp-server-fetch
kinthic mcp enable myserver
```

See [PLUGIN_DEVELOPMENT.md](../PLUGIN_DEVELOPMENT.md) for when to use MCP vs skills vs tool plugins.

---

## Serving Silex memory (MCP server mode)

Kinthic can **expose** the Silex memory engine as an MCP server so Claude Desktop, Cursor, or other agents use your persistent brain.

### Quick start

1. Start the daemon (gateway mounts MCP at `/mcp`):

```bash
kinthic daemon install
kinthic daemon start
```

2. Connect Claude Desktop / Cursor:

```bash
kinthic mcp print-config --client claude
```

Paste the JSON into your MCP client config, or run:

```bash
kinthic mcp serve --stdio
```

### HTTP endpoint

When the gateway is running:

- URL: `http://127.0.0.1:8000/mcp` (Streamable HTTP)
- Auth: `x-kinthic-api-key` or `Authorization: Bearer <key>`

### Tools exposed

| Tool | Purpose |
|------|---------|
| `silex_recall` | Hybrid memory retrieval (primary) |
| `silex_search` | Keyword FTS search |
| `silex_remember` | Full A-MAC admission with metadata |
| `silex_remember_explicit` | Direct fact storage |
| `silex_forget` | Delete by ID (`confirm=true`) |
| `silex_get_memory` | Fetch one memory |
| `silex_list_memories` | Paginated list |
| `silex_graph_recall` | Knowledge graph context |
| `silex_memory_health` | Engine stats |

See [mcp-server-rfc.md](mcp-server-rfc.md) for the full contract.

### CLI

| Command | Purpose |
|---------|---------|
| `kinthic mcp serve --stdio` | stdio bridge for desktop clients |
| `kinthic mcp print-config` | Paste-ready client JSON |
| `kinthic doctor` | MCP endpoint + audit log status |

### Audit log

All MCP tool calls are logged to `~/.kinthic/logs/mcp-audit.ndjson`.

### Benchmark

```bash
kinthic benchmark recall --seed 42
python -m benchmarks.memory_recall.harness --noise 50 --conditions aged_21d
python scripts/mcp_recall_benchmark.py
```

See [docs/benchmarks/memory-recall.md](benchmarks/memory-recall.md).
