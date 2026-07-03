# MCP integration

Kinthic can connect to external **Model Context Protocol (MCP)** servers and expose their tools to the agent alongside built-in tools.

## Quick start

After `kinthic onboard`, enable a preset:

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
