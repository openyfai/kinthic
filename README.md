# ARIA (Bringing AGI to the Public)

**What this is:** ARIA is an **experimental, local-first AI agent** from **[OpenYF AI](https://github.com/openyfai)**. It combines chat with **persistent memory**, a living **knowledge graph**, governed **tools**, an optional **web dashboard**, and **Telegram** integration. Sources and updates live at **[github.com/openyfai/aria](https://github.com/openyfai/aria)**.

**Who it's for:** people who want **more than a raw chat completion** — operators who configure providers, approvals, identity, and (optionally) 24/7 proactive behavior behind clear safety defaults.

We are building in public; you can adopt it as-is, customize skills, or follow the codebase as the project evolves.

---

**In one sentence:** install once, run **`aria setup`** or open the dashboard with **`aria web`**, optionally pair Telegram, and chat.

## Quick start (PyPI — recommended)

You need **Python 3.11 or newer** (latest stable 3.x is recommended).

```bash
pip install "openyfai-aria[full]"
```

**Option A — browser setup (default):**

```bash
aria web
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**, complete provider and safety settings in the UI, then use Chat (and Graph / Operator / Settings as you like).

**Option B — terminal setup only:**

```bash
aria setup
```

Then run **`aria`** for the terminal agent or **`aria web`** for the dashboard.

**Optional:** background daemon (non-Windows / see notes in CLI): **`aria start`**

PyPI wheels include a **pre-built dashboard** when published through the project’s release workflow; you should **not** need Node or `npm` for a normal install.

Try a first prompt such as: *Analyze this repo and build a knowledge graph of the architecture.*

More detail: [`docs/quickstart.md`](docs/quickstart.md).

## Developing from source (contributors)

Clone the repo and use an editable install when you are changing Python or the Next.js UI:

```bash
git clone https://github.com/openyfai/aria.git && cd aria
pip install -e ".[full,dev]"
```

If you change the **web frontend**, build it once so `aria web` can serve `aria-ui/out` from your checkout:

```bash
cd aria-ui && npm install && npm run build && cd ..
```

Release builds (CI) copy this output into `aria/web_dist/` for **PyPI** wheels — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Why ARIA

- Local-first memory and state backed by SQLite.
- A visible graph of what the agent believes.
- Provider and model choice from the setup wizard or `aria setup`.
- Operator controls for approvals, usage, Telegram pairing, and remote access.
- Markdown skills that let contributors extend behavior without editing Python.

## More ways to run

| Path | When to use |
|------|-------------|
| **Web UI** (`aria web`) | Default: finish setup in the browser. |
| **Terminal agent** (`aria` after setup) | Keyboard-first use. |
| **CLI setup only** (`aria setup`) | You prefer not to use the web wizard once. |
| **Docker** | Deploy to a server or share on a LAN; needs `.env` and a web API key. See [`docs/quickstart.md`](docs/quickstart.md#deploy--server-docker). |

## Requirements

- **Python** `>=3.11` (matches package metadata on PyPI).
- **Node 20+** — only if you develop or rebuild `aria-ui/` from source (not required for standard `pip install` wheels).
- **Docker** — optional.

## Safe defaults

- Tool approvals are on.
- Terminal execution is off.
- Direct code writes are off.
- Background actions are off.
- Remote web binds require `ARIA_WEB_API_KEY`.
- Telegram is deny-by-default until paired from **Operator**.

Read [`SECURITY.md`](SECURITY.md) before exposing ARIA beyond localhost.

## Power user / troubleshooting

If chat or setup fails after you have saved provider keys, see [`docs/quickstart.md`](docs/quickstart.md#power-user--troubleshooting-commands) for `aria doctor`, `aria doctor --ping`, and related commands. You do not need these for a first successful run.

## Provider support

Gemini, OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Groq, Ollama, and local OpenAI-compatible endpoints. Settings come from the wizard, `aria setup`, `data/` runtime files, or environment variables.

## Skills

Add a Markdown file under `skills/`, restart ARIA, and the agent can use that workflow. Start with [`skills/repo_researcher.md`](skills/repo_researcher.md) or [`skills/README.md`](skills/README.md).

## Repository guide

- Core loop: `aria/core/cognitive_loop.py`
- Providers: `aria/llm/`
- Web backend: `scripts/web_server.py`
- CLI: `scripts/cli.py`
- Telegram: `scripts/telegram_bot.py`
- Web UI: `aria-ui/src/`
- Packaged static UI (release builds): `aria/web_dist/`
- Skills: `skills/`

## Development

```bash
python -m pytest tests
ruff check .
cd aria-ui && npm install && npm run lint && npm run build
```

## Project docs

- [`docs/quickstart.md`](docs/quickstart.md) — install paths, Docker, troubleshooting  
- [`CONTRIBUTING.md`](CONTRIBUTING.md)  
- [`SECURITY.md`](SECURITY.md)  
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)  
- [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md) — phased roadmap  
- [`docs/planning/launch-checklist.md`](docs/planning/launch-checklist.md) — pre-public-release checklist  
- [`docs/planning/launch-issue-backlog.md`](docs/planning/launch-issue-backlog.md) — seeded “good first issue” ideas  
- [`CHANGELOG.md`](CHANGELOG.md)

## License

Apache-2.0. See [`LICENSE`](LICENSE).
