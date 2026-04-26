# ARIA: The "OpenClaw" Launch Roadmap

With the 7-phase core engine complete, ARIA is structurally ready. This roadmap covers the **Productization & Virality** phase. The goal is to make ARIA accessible, visually stunning, and highly extensible to drive community adoption upon open-source launch.

---

## Phase A: The Ingress Adapters (Telegram + CLI)
*Status: Ready to build*

Currently, ARIA is hardcoded into `scripts/run.py`. We will decouple the `CognitiveLoop` using the "Adapter Pattern" seen in OpenClaw, allowing ARIA to live across multiple interfaces simultaneously.

1. **Refactor `run.py`**: Extract the terminal-specific UI logic into a proper `TerminalAdapter`.
2. **Build `scripts/telegram_bot.py`**: 
    - Use `python-telegram-bot` for polling.
    - Route incoming Telegram messages into `CognitiveLoop.process()`.
    - Format ARIA's rich markdown responses for Telegram's chat UI.
    - *Viral Hook:* Users can text their personal AGI from anywhere to execute tasks on their home server.

## Phase B: Obsidian-Style Knowledge Graph (The Visual "Wow" Factor)
*Status: Pending*

To visually prove that ARIA is building a World Model, we will render her SQLite knowledge graph as an interactive 3D/2D node network.

1. **Build a Local Web Server**: Use FastAPI (`scripts/web_server.py`) to expose a single endpoint: `/api/graph`.
2. **Web Dashboard (`aria/ui/static/index.html`)**: 
    - Use `3d-force-graph` or `vis.js` to render the nodes (Concepts) and edges (Causal Links).
    - Color-code nodes by domain.
    - *Viral Hook:* Record a timelapse of the graph growing organically as ARIA learns new concepts during a conversation.

## Phase C: The "Skills" Ecosystem (Community Growth)
*Status: Pending*

Taking inspiration from OpenClaw, we will separate **Tools** (executable Python) from **Skills** (Markdown instruction files).

1. **Create the `skills/` Directory**: A folder where users drop `[skill_name].md` files.
2. **Build the `SkillLoader`**: ARIA dynamically reads these markdown files on startup.
3. **Prompt Injection**: If a user asks "Help me design a logo", ARIA pulls the `logo_design.md` skill and loads its specific instructions and tool workflows into her context.
4. *Viral Hook:* Developers don't need to write Python to teach ARIA. They just write Markdown. This encourages massive community sharing of "Skill Packs."

## Phase D: Terminal UI Polish (The Hacker Aesthetic)
*Status: Pending*

We will upgrade the terminal interface from basic text printing to a professional, glitch-free Terminal UI (TUI).

1. **Split-Screen Layout**: Use `rich.layout` to split the terminal. 
    - Left side: Chat history.
    - Right side: Live streaming of ARIA's "Internal Monologue" (Critique, Tool Calls, Hypotheses).
2. **Live Spinners & Streaming**: Implement safe line-clearing to ensure progress spinners do not break the terminal layout when large text blocks are rendered.

## Phase E: The Open-Source Launch Kit
*Status: Pending*

1. **Dockerization**: A `docker-compose.yml` that spins up the Core Engine, the Web Graph server, and the Telegram bot in one command.
2. **The README**: A beautiful GitHub README featuring:
    - The Architecture Stack diagram.
    - GIFs of the Telegram bot and the expanding Knowledge Graph.
    - Clear instructions on how to write custom `.md` Skills.

---

### Suggested Execution Order:
1. **Phase A (Telegram)**: It’s the fastest to build and proves the adapter architecture works.
2. **Phase B (Graph)**: Generates the visual content needed for marketing.
3. **Phase C (Skills)**: Prepares the repository for community contributions.
