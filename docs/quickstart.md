# Kronos quick start

This guide is the **single golden path** from zero to a working agent.

**Pre-launch gate (Telegram-first):** [telegram-launch-checklist.md](telegram-launch-checklist.md)

## Prerequisites

- **Linux / macOS**, or **WSL2 on Windows** ([WSL setup guide](wsl-setup.md))
- Python 3.11+ and Git (the installer can install these on Ubuntu)

## Step 1 — Install

```bash
curl -fsSL https://kronos.openyf.dev/install.sh | bash
source ~/.bashrc   # or ~/.zshrc
```

## Step 2 — Onboard

```bash
kronos onboard
```

The wizard walks through:

1. LLM provider + API key (with live ping)
2. Core skills (jokes, repo research, release notes, Telegram setup, daily briefing)
3. Optional Telegram pairing
4. Optional MCP servers (filesystem / fetch)

## Step 3 — Run

```bash
kronos
```

Try: *Analyze this repo and summarize the architecture.*

For Telegram:

```bash
kronos telegram run
```

## Skills CLI

```bash
kronos skills list
kronos skills search docker
kronos skills install repo_onboard
kronos skills reload
```

Inside a session: `:skills` and use the `skill_view` tool for full instructions.

## MCP

```bash
kronos mcp add filesystem --preset filesystem
kronos mcp enable filesystem
kronos mcp test filesystem
```

Details: [mcp.md](mcp.md). In-session: `:mcp list`, `:mcp reload`.

## Verify

```bash
kronos doctor
kronos doctor --ping
```

## Developing from source

```bash
git clone https://github.com/openyfai/kronos.git
cd kronos
pip install -e ".[dev,mcp]"
kronos onboard
kronos
```

## Demo script

Record a golden-path demo:

1. `curl -fsSL …/install.sh | bash`
2. `kronos onboard` (pick Gemini + skip Telegram or pair live)
3. `kronos` → ask *tell me a joke* (uses `tell_joke` skill via `skill_view`)
4. `kronos skills list`
5. `kronos doctor --ping`

Outline: [demo-script.md](demo-script.md)

## Troubleshooting

| Command | Purpose |
|---------|---------|
| `kronos doctor --ping` | Live API check |
| `kronos skills reload` | Reload skills without restart |
| `kronos mcp test <name>` | Test MCP server |
| `kronos setup` | Legacy wizard (prefer `onboard`) |

## Docker (Telegram daemon)

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USERS, GEMINI_API_KEY
docker compose --profile telegram up --build
```
