# ARIA quick start

This guide expands on the [README](../README.md) with concrete commands and optional paths.

## Golden path (recommended) — install from PyPI

You need **Python 3.11+** (latest stable 3.x is fine). For a normal **PyPI** install you do **not** need Node; the published wheel includes a pre-built dashboard from the release pipeline.

```bash
pip install openyfai-aria
```

**Browser onboarding:**

```bash
aria web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), complete provider, model, API keys, and safety toggles in the UI.

**Or terminal-only setup first:**

```bash
aria setup
```

Then run **`aria web`** or the terminal agent with **`aria`**.

**Finish setup entirely in the browser** if you use `aria web` first: you do **not** need `aria setup` unless you prefer the CLI wizard.

Try a first prompt such as: *Analyze this repo and build a knowledge graph of the architecture.*

Demo scripts: [`scripts/demo.py`](../scripts/demo.py), recording outline: [`docs/demo-script.md`](demo-script.md).

---

## Developing from source

If you are **contributing** or running from a **git clone**, use an editable install and (when you change the frontend) rebuild `aria-ui`:

```bash
git clone https://github.com/openyfai/aria.git
cd aria
pip install -e ".[dev]"
cd aria-ui && npm install && npm run build && cd ..
aria web
```

PyPI releases run CI that copies **`aria-ui/out`** into **`aria/web_dist/`** before building the wheel. To mirror that locally before `python -m build`, see [`CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## One-line mental model

1. Run **`aria web`** (or **`aria setup`** then **`aria web`**)
2. Complete **setup**
3. Use **Chat** (and **Graph**, **Operator**, **Settings** when you want more)

Optional later: **Telegram** from **Operator** (pairing code), Docker for a server, or **`aria doctor --ping`** if the model connection fails.

---

## Terminal agent (no web)

After install and `aria setup` (or after web setup wrote `data/`):

```bash
aria
```

---

## Deploy / server (Docker)

For remote access you should set a **web API key** and read [`SECURITY.md`](../SECURITY.md).

1. Copy `.env.example` to `.env`.
2. Set at least:
   - `ARIA_WEB_HOST=0.0.0.0`
   - `ARIA_WEB_API_KEY=<long-random-secret>`
   - One provider key, e.g. `GEMINI_API_KEY`
3. Run:

```bash
docker compose --profile web up --build
```

Open `http://localhost:8000`, paste the **web API key**, then complete setup.

---

## Power user / troubleshooting commands

Use these **after** the basics work, or when something breaks.

| Command | Purpose |
|--------|---------|
| `aria doctor` | Local settings and security summary |
| `aria doctor --ping` | Live check that the configured provider responds |
| `aria models` | List providers and model ids |
| `aria telegram pair` | Create a Telegram pairing code (then `/start CODE` with your bot) |
| `aria telegram run` | Run the Telegram bot (separate process) |
| `python -m build` | Smoke-test the Python package build |

---

## Requirements summary

- **Python** `>=3.11`
- **Node 20+** — only when building `aria-ui/` from source (contributors).
- **Docker** — optional

---

## Identity & Tone

You can customize how ARIA speaks to you. 
Open the **Settings** view in the web UI to change the **Assistant name** or define a custom **Persona** (e.g. "Speak like a senior research engineer: high signal-to-noise ratio, zero fluff"). This overrides the default helpful tone but retains all cognitive and safety guardrails.

---

## Where to read next

- [`SECURITY.md`](../SECURITY.md) — before exposing ARIA beyond localhost  
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — develop, test, and release  
- [`skills/README.md`](../skills/README.md) — Markdown skills
