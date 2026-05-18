# VYN by OpenYF AI

> Building intelligent systems. One phase at a time.

VYN is an open source AI agent that lives on your machine, remembers everything you tell it, builds a knowledge graph of what it learns, improves itself over time, and works 24/7 — even while you sleep.

Not a chatbot. A cognitive agent with persistent memory, a world model, tool use, and a self-improvement loop. Built openly by [YF](https://github.com/openyfai) as the first step toward general intelligence.

**Powered by ARIA** — the internal memory engine that manages VYN's knowledge graph, causal world model, and long-term memory.

[![PyPI](https://img.shields.io/pypi/v/openyfai-vyn)](https://pypi.org/project/openyfai-vyn/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green)](https://python.org)

---

## What makes VYN different

Most AI tools forget you the moment the conversation ends. VYN doesn't.

- **Persistent memory** — remembers everything across sessions, forever, stored locally on your machine
- **Knowledge graph** — builds a causal map of what it learns, not just a list of facts
- **Self-improvement loop** — critiques its own responses and retries when unsatisfied
- **Tool use** — web search, file access, code execution, browser
- **Multi-agent debate** — two instances argue opposing views to find truth
- **Telegram integration** — lives in your phone, works while your laptop is closed
- **Your data, your machine** — nothing leaves your device

---

## Install

```bash
pip install openyfai-vyn
vyn setup
```

Open **http://127.0.0.1:8000** and start talking.

> **Windows users:** If `vyn` is not recognized after install, close and reopen your terminal. If blocked by Device Guard, run `python -m scripts.cli web` instead.

---

## The roadmap

VYN is being built in 7 phases, in public, with full documentation of every decision.

| Phase | What it builds | Status |
|-------|---------------|--------|
| 01 | Cognitive core + persistent memory | ✅ Complete |
| 02 | World model — causal knowledge graph | ✅ Complete |
| 03 | Self-improvement loop | ✅ Complete |
| 04 | Multi-agent debate | ✅ Complete |
| 05 | Tool use + embodiment | ✅ Complete |
| 06 | Transfer + generalization | ✅ Complete |
| 07 | Recursive self-improvement | 🔄 In progress |

Full roadmap: [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md)

---

## More ways to run

| Path | When to use |
|------|-------------|
| **Web UI** (`vyn web`) | Default: finish setup in the browser. |
| **Terminal agent** (`vyn` after setup) | Keyboard-first use. |
| **CLI setup only** (`vyn setup`) | You prefer not to use the web wizard. |
| **Docker** | Deploy to a server or share on a LAN. See [`docs/quickstart.md`](docs/quickstart.md#deploy--server-docker). |

---

## Provider support

Gemini, OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Groq, Ollama, and local OpenAI-compatible endpoints. Choose your provider during `vyn setup` or change it anytime in settings.

---

## Skills

Add a Markdown file under `~/.vyn/skills/`, restart VYN, and the agent can use that workflow without touching Python.

---

## Safe defaults

VYN ships locked down. Nothing runs without your approval.

- Tool approvals are **on**
- Terminal execution is **off**
- Direct code writes are **off**
- Background actions are **off**
- Remote web access requires an API key
- Telegram is deny-by-default until paired from **Operator**

Read [`SECURITY.md`](SECURITY.md) before exposing VYN beyond localhost.

---

## Requirements

- **Python** `>=3.11`
- **Node 20+** — only if you rebuild `aria-ui/` from source (not needed for `pip install`)
- **Docker** — optional

---

## Contributing

VYN is built in public. Every decision is documented, every phase is open. Contributors welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) and the seeded issues in [`docs/planning/launch-issue-backlog.md`](docs/planning/launch-issue-backlog.md) for good first tasks.

Follow the journey on X: [@openyfai](https://x.com/openyfai)

---

## Repository guide

| Path | What lives here |
|------|----------------|
| `aria/core/cognitive_loop.py` | Core cognitive pipeline (ARIA engine) |
| `aria/llm/` | LLM providers |
| `aria/memory/` | Memory store + retrieval (ARIA engine) |
| `aria/world/` | Knowledge graph + hypotheses (ARIA engine) |
| `scripts/web_server.py` | Web backend (FastAPI) |
| `scripts/cli.py` | CLI entrypoint (`vyn` commands) |
| `scripts/telegram_bot.py` | Telegram integration |
| `aria-ui/src/` | Web UI (Next.js) |

---

## Development

```bash
git clone https://github.com/openyfai/vyn.git && cd vyn
pip install -e ".[dev]"
python -m pytest tests
ruff check .
```

To rebuild the web UI from source:

```bash
cd aria-ui && npm install && npm run build && cd ..
```

---

## Project docs

- [`docs/quickstart.md`](docs/quickstart.md) — install paths, Docker, troubleshooting
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md)
- [`CHANGELOG.md`](CHANGELOG.md)

---

## Migrating from openyfai-aria

If you were using the old package:

```bash
pip uninstall openyfai-aria
pip install openyfai-vyn
```

Your existing data in `~/.vyn/` (or your old `data/` folder) will be detected and migrated automatically on first run.

---

## License

AGPL-3.0. See [`LICENSE`](LICENSE).

VYN is licensed under the AGPL-3.0 License. This ensures the project remains truly open-source and prevents proprietary network-based exploitation.

---

*OpenYF AI — building intelligent systems, in public.*
