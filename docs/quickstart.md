# Kinthic quick start

This guide is the **single golden path** from zero to a working agent.

**Pre-launch gate (Telegram-first):** [telegram-launch-checklist.md](telegram-launch-checklist.md)

## Prerequisites

- **Linux / macOS**, or **WSL2 on Windows** ([WSL setup guide](wsl-setup.md))
- Python 3.11+ and Git (the installer can install these on Ubuntu)

## Step 1 — Install

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
source ~/.bashrc   # or ~/.zshrc
```

## Step 2 — Initialize

```bash
kinthic init
```

`kinthic init` and `kinthic setup` are aliases for the same wizard.

The wizard walks through:

1. LLM provider + API key (with live ping)
2. Core skills (jokes, repo research, release notes, Telegram setup, daily briefing)
3. Optional Telegram pairing
4. Optional MCP servers (filesystem / fetch)

## Step 3 — Run

```bash
kinthic
```

Try: *Analyze this repo and summarize the architecture.*

For Telegram:

```bash
kinthic channels telegram run
```

## Skills CLI

```bash
kinthic skills list
kinthic skills search docker
kinthic skills install repo_onboard
kinthic skills reload
```

Inside a session: `:skills` and use the `skill_view` tool for full instructions.

## MCP

```bash
kinthic mcp add filesystem --preset filesystem
kinthic mcp enable filesystem
kinthic mcp test filesystem
```

Details: [mcp.md](mcp.md). In-session: `:mcp list`, `:mcp reload`.

## Verify

```bash
kinthic doctor
kinthic doctor --ping
```

### Verify memory (optional)

Prove Silex retrieval with the published needle-in-haystack benchmark (~1 min with 500 distractors):

```bash
kinthic benchmark recall --seed 42
```

Or run the live demo script (good for a 60s recording):

```bash
python benchmarks/memory_recall/demo.py
```

What the numbers mean: [benchmarks/memory-recall.md](benchmarks/memory-recall.md).

## Developing from source

```bash
git clone https://github.com/openyfai/kinthic.git
cd kinthic
pip install -e ".[dev,mcp]"
kinthic init
kinthic
```

## Demo script

Record a golden-path demo:

1. `curl -fsSL …/install.sh | bash`
2. `kinthic init` (pick Gemini + skip Telegram or pair live)
3. `kinthic` → ask *tell me a joke* (uses `tell_joke` skill via `skill_view`)
4. `kinthic skills list`
5. `kinthic doctor --ping`

Outline: [demo-script.md](demo-script.md)

## Troubleshooting

| Command | Purpose |
|---------|---------|
| `kinthic doctor --ping` | Live API check |
| `kinthic skills reload` | Reload skills without restart |
| `kinthic mcp test <name>` | Test MCP server |
| `kinthic setup` | Legacy wizard (prefer `onboard`) |

## Docker (Telegram daemon)

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USERS, GEMINI_API_KEY
docker compose --profile telegram up --build
```
