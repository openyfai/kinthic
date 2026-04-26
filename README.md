# ARIA
**Adaptive Reasoning & Intelligence Architecture**

ARIA is a sovereign, locally-running AI agent that actually *thinks*. 

Unlike traditional chatbots that simply answer prompts, ARIA possesses a true **Causal World Model**, maintains persistent memory across sessions, and operates on a recursive self-improvement loop. She doesn't just store data; she understands the relationships between concepts, detects logical contradictions, and spawns internal multi-agent debates to resolve her own uncertainty.

![ARIA Terminal Architecture](https://via.placeholder.com/800x400.png?text=ARIA+Terminal+|+Split-Screen+Hacker+UI)

---

## 🌟 Why ARIA? (The OpenClaw Evolution)

Inspired by the viral success of autonomous agents, ARIA takes local execution a step further by prioritizing **cognitive reasoning and safety** over blind task execution. 

* **The Safety Lock:** ARIA can analyze her own failures and propose architectural upgrades to her own codebase, but she requires *explicit human approval* to implement them.
* **The Visual Brain:** ARIA features an Obsidian-style local web dashboard where you can visually watch her neural network (Knowledge Graph) expand and make connections in real-time as you talk to her.
* **Markdown "Skills":** Don't know Python? You don't need to. Teach ARIA new, complex workflows simply by dropping a `.md` file into her `skills/` folder.

---

## 🧠 The 7-Phase Cognitive Stack

ARIA was built meticulously over 7 phases to achieve generalized reasoning:

1. **Memory & Cognitive Core:** Tracks goals and persists conversation context via a local SQLite database.
2. **The World Model:** Builds an active, causal Knowledge Graph of concepts and relationships in real-time.
3. **The Self-Improvement Loop:** An internal "Critic" LLM grades every drafted response for accuracy and depth. If it fails, she rewrites it.
4. **Multi-Agent Debate:** When she detects a contradiction, she spawns two separate AI agents to debate the truth, judged by a third agent.
5. **Embodiment (Tool Use):** Can execute external code, search the web, and read local files.
6. **Cross-Domain Generalization:** Abstracts specific facts into universal laws, allowing her to make brilliant analogies across completely unrelated fields.
7. **Recursive Self-Improvement:** Tracks her own failures, benchmarks her intelligence, and formally proposes code upgrades.

---

## 🚀 Quick Start (Docker)

The easiest way to run ARIA, the Visual Graph, and the Telegram Bot is via Docker.

1. Clone the repo:
   ```bash
   git clone https://github.com/yourusername/aria-agi.git
   cd aria-agi
   ```

2. Create your environment file:
   ```bash
   cp .env.example .env
   ```
   *Add your `GEMINI_API_KEY` and `TELEGRAM_BOT_TOKEN` (from @BotFather) to the `.env` file.*

3. Spin up the ecosystem:
   ```bash
   docker-compose up -d
   ```

**What just happened?**
* 📱 Your **Telegram Bot** is now online. Text her from your phone.
* 🌐 The **Visual World Model** is live. Open `http://localhost:8000` to watch her brain grow as you talk to her.

---

## 💻 Running the Split-Screen CLI

If you prefer the hacker aesthetic, run the split-screen Terminal UI locally:

```bash
pip install -e .
python scripts/run.py
```
*Note: The CLI splits your terminal. On the left is the chat, and on the right is a live-streaming log of her "Internal Monologue" and self-reflections.*

---

## 🛠️ The Markdown Skills Ecosystem

You can teach ARIA new behaviors without writing a single line of code. 

1. Create a markdown file: `skills/write_twitter_thread.md`.
2. Write your instructions in plain English:
   ```markdown
   # Twitter Thread Writer
   When asked to write a thread, follow this exact workflow:
   1. Write a hook.
   2. Provide 3 data points.
   3. Write a conclusion.
   ```
3. Restart ARIA. She will instantly absorb this skill into her cognitive loop and apply the workflow whenever you ask her to write a thread.

---

## 🔒 Privacy & Data

ARIA is completely sovereign. Her SQLite brain (`data/aria_memory.db`) lives strictly on your local machine. No chat logs or knowledge graphs are ever sent to a third-party server (except the LLM API calls to Gemini).

## License
MIT License.
