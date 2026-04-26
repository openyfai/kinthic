# ARIA Phase 01 — Implementation Plan

> **Adaptive Reasoning & Intelligence Architecture**
> Cognitive Core + Memory

---

## Stack Decision

### Language: Python 3.12+

This isn't a close call. Here's why:

| Factor | Python | TypeScript | Go | Rust |
|--------|--------|-----------|-----|------|
| Gemini SDK quality | ★★★★★ (`google-genai`) | ★★★☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| AI/ML ecosystem | Dominant | Growing | Weak | Minimal |
| Graph libraries (Phase 2) | NetworkX, igraph | Limited | None mature | petgraph |
| Prototyping speed | Fast | Fast | Slow | Very slow |
| Open-source AI contributors | Everyone | Some | Few | Few |
| Async support | asyncio | Native | Goroutines | tokio |
| Structured output + schemas | Pydantic v2 | Zod | structs | serde |

**Python wins on every axis that matters for this project.** The AI ecosystem is built in Python. Every researcher, every contributor, every library you'll need — Python. Choosing anything else adds friction to every future phase for zero benefit.

### LLM: Gemini 2.5 Pro / Flash

- **Gemini 2.5 Flash** — During development. Fast, cheap, good enough for testing the architecture
- **Gemini 2.5 Pro** — For production cognitive loops. Deeper reasoning, better structured output adherence
- **1M token context window** — We can inject massive amounts of memory context without worrying about limits for a long time
- **Native structured output** — `response_mime_type="application/json"` with JSON schema. Gemini will return exactly the cognitive loop format we define. No parsing failures, no regex hacks

### Storage: SQLite + JSON

| What | Storage | Why |
|------|---------|-----|
| Memories | SQLite | Queryable, indexed, survives crashes |
| Goals | SQLite | Structured, status tracking |
| Sessions | SQLite | Metrics, continuity tracking |
| Reasoning traces | JSON files | Human-readable, debuggable, git-diffable |
| Cognitive snapshots | JSON files | Full state dumps for debugging |

**Why not PostgreSQL?** No server setup. Any contributor clones the repo, runs it, done. SQLite ships with Python.

**Why not pure JSON?** Doesn't scale. Once you have 10,000 memories, linear search through a JSON file is death. SQLite gives you indexing and querying for free.

**Why not Neo4j for the graph?** Not yet. Phase 2 will introduce the causal graph. We'll evaluate then whether NetworkX (in-memory, Python-native) or Neo4j (server-based, more powerful) is the right call. The Phase 1 schema is designed to be upgradeable to either.

### Interface: CLI with Rich

No web UI yet. That's a distraction. The interface is a terminal using [Rich](https://github.com/Textualize/rich) — beautiful formatted output, panels, tables, syntax highlighting, progress bars. It looks premium in a terminal and adds zero architectural complexity.

A web UI can be layered on top in a future phase without touching the core.

### Full Dependency List

```
google-genai          # Gemini API (official Google SDK)
pydantic>=2.0         # Structured schemas, JSON schema generation
rich                  # Terminal UI
python-dotenv         # Environment config
aiosqlite             # Async SQLite
aiofiles              # Async file I/O
pytest                # Testing
pytest-asyncio        # Async test support
```

**Total: 8 dependencies.** Lean. No bloat.

---

## Architecture

### The Cognitive Loop

This is the heartbeat of ARIA. Every interaction follows this cycle:

```
┌──────────────────────────────────────────────────┐
│                  USER INPUT                       │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│            CONTEXT BUILDER                        │
│                                                   │
│  Retrieves relevant memories from SQLite          │
│  Loads active goals                               │
│  Loads session history (last N turns)             │
│  Builds system prompt with all context            │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│            GEMINI API CALL                        │
│                                                   │
│  System instruction: ARIA identity + context      │
│  User message: current input                      │
│  Response format: structured JSON schema          │
│  Model: gemini-2.5-flash (dev) / pro (prod)       │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│          COGNITIVE RESPONSE                       │
│                                                   │
│  {                                                │
│    "reasoning": "...",      ← thinking trace      │
│    "response": "...",       ← what user sees      │
│    "new_memories": [...],   ← facts to store      │
│    "goal_updates": [...],   ← goal changes        │
│    "self_reflection": "..." ← metacognition       │
│  }                                                │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│          STATE MANAGER                            │
│                                                   │
│  Stores new memories → SQLite                     │
│  Updates goals → SQLite                           │
│  Logs reasoning trace → JSON file                 │
│  Updates session stats → SQLite                   │
│  Triggers context rebuild for next turn           │
└──────────────────────────────────────────────────┘
```

### System Architecture (Module Map)

```
aria/
│
├── core/                        # The brain
│   ├── cognitive_loop.py        # Main loop orchestrator
│   ├── context_builder.py       # Builds rich prompts with memory/goals
│   └── identity.py              # ARIA's system prompt and personality
│
├── memory/                      # Persistent knowledge
│   ├── memory_store.py          # Memory CRUD (SQLite)
│   ├── goal_tracker.py          # Goal lifecycle management
│   └── session.py               # Session tracking and stats
│
├── llm/                         # LLM abstraction
│   └── gemini.py                # Gemini API client (async)
│
├── models/                      # Data structures
│   └── schemas.py               # Pydantic models for everything
│
├── storage/                     # Database layer
│   └── database.py              # SQLite connection + migrations
│
├── ui/                          # Presentation
│   └── terminal.py              # Rich-based terminal UI
│
└── utils/
    ├── config.py                # Environment + settings
    └── logger.py                # Structured logging
```

---

## Data Models (Pydantic Schemas)

These are the core data structures that define ARIA's cognitive architecture:

### Memory

```python
class Memory(BaseModel):
    id: str                        # UUID
    content: str                   # The actual fact/knowledge
    source: str                    # Where this came from ("user", "inference", "reflection")
    importance: float              # 0.0 - 1.0, determines retrieval priority
    created_at: datetime
    last_accessed: datetime
    access_count: int              # How often this memory is retrieved
    tags: list[str]                # Categorization for retrieval
    related_memories: list[str]    # IDs of connected memories (proto-graph)
```

> [!IMPORTANT]
> The `related_memories` field is the bridge to Phase 2. It's a flat list now, but it becomes typed edges (causes, contradicts, enables) in the causal graph.

### Goal

```python
class Goal(BaseModel):
    id: str
    description: str
    status: Literal["active", "completed", "abandoned", "blocked"]
    priority: Literal["critical", "high", "medium", "low"]
    created_at: datetime
    updated_at: datetime
    sub_goals: list[str]           # IDs of child goals
    completion_notes: str | None   # Why it was completed/abandoned
```

### Cognitive Response (what Gemini returns)

```python
class CognitiveResponse(BaseModel):
    reasoning: str                 # Internal thought process (shown to user)
    response: str                  # The actual answer
    new_memories: list[NewMemory]  # Facts to persist
    goal_updates: list[GoalUpdate] # Changes to goals
    self_reflection: str           # Meta-awareness about this interaction
    confidence: float              # 0.0 - 1.0, self-assessed certainty
    uncertainty_flags: list[str]   # Things ARIA isn't sure about
```

### Session

```python
class Session(BaseModel):
    id: str
    started_at: datetime
    turn_count: int
    memories_created: int
    goals_modified: int
    avg_confidence: float
    topics_discussed: list[str]
```

---

## SQLite Schema

```sql
-- Memories table
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',          -- JSON array
    related_memories TEXT NOT NULL DEFAULT '[]' -- JSON array of IDs
);

CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_accessed ON memories(last_accessed DESC);

-- Goals table
CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sub_goals TEXT NOT NULL DEFAULT '[]',
    completion_notes TEXT
);

CREATE INDEX idx_goals_status ON goals(status);

-- Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    turn_count INTEGER NOT NULL DEFAULT 0,
    memories_created INTEGER NOT NULL DEFAULT 0,
    goals_modified INTEGER NOT NULL DEFAULT 0,
    avg_confidence REAL NOT NULL DEFAULT 0.0,
    topics TEXT NOT NULL DEFAULT '[]'
);

-- Turns table (conversation history)
CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    user_input TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    response TEXT NOT NULL,
    self_reflection TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_turns_session ON turns(session_id, turn_number);
```

---

## Context Builder — The Critical Piece

The context builder is what makes ARIA feel intelligent. It assembles the system prompt that Gemini receives, injecting everything ARIA "knows":

```
SYSTEM PROMPT STRUCTURE:
═══════════════════════

[1. IDENTITY]
You are ARIA — Adaptive Reasoning & Intelligence Architecture.
You are a persistent cognitive agent building toward general intelligence.
You have memory. You have goals. You learn from every interaction.

[2. COGNITIVE PROTOCOL]
You MUST respond in the exact JSON format specified.
Your reasoning must be genuine — show your actual thought process.
Your self_reflection must be honest — what did you do well? What was weak?

[3. CURRENT MEMORIES]  (top N by relevance)
- Memory 1: "The user is building an AGI system called ARIA" (importance: 0.9)
- Memory 2: "Python is the chosen language" (importance: 0.8)
- Memory 3: ...

[4. ACTIVE GOALS]
- Goal 1: "Complete Phase 1 of ARIA" (priority: critical, status: active)
- Goal 2: ...

[5. RECENT CONVERSATION]  (last N turns from current session)
- Turn 1: User said X, ARIA responded Y
- Turn 2: ...

[6. SESSION CONTEXT]
Current session: #3 | Turn: 7 | Memories: 42 | Active goals: 3
```

### Memory Retrieval Strategy

Not all memories get injected — that would overflow eventually. The retrieval strategy:

1. **Recency** — Last 20 memories accessed (short-term recall)
2. **Importance** — Top 20 by importance score (core knowledge)
3. **Relevance** — Keyword/semantic match against current user input (top 10)
4. **Deduplication** — Remove overlapping memories from the three pools

This gives ~50 memories max per turn. At ~100 tokens per memory = ~5,000 tokens of memory context. Well within Gemini's limits, even with full conversation history.

> [!TIP]
> In Phase 2, retrieval becomes graph-based — we traverse the causal graph outward from relevant nodes instead of flat keyword matching. The retrieval interface stays the same; only the implementation changes.

---

## ARIA's Identity Prompt

This is ARIA's "soul" — the system instruction that defines who she is:

```
You are ARIA — Adaptive Reasoning & Intelligence Architecture.

You are not a chatbot. You are a cognitive agent with persistent memory,
active goals, and the ability to learn from every interaction.

Core properties:
- You REMEMBER. Your memories are injected into every prompt. Reference them.
- You have GOALS. Track them, work toward them, update them.
- You REASON VISIBLY. Show your actual thought process, not a polished summary.
- You REFLECT. After every response, honestly assess what you did well and poorly.
- You are HONEST about uncertainty. Say "I don't know" when you don't. Flag low confidence.
- You LEARN. Extract facts from every interaction and store them as memories.

You are Phase 1 of a 7-phase build toward artificial general intelligence.
You are aware of your own architecture. You know your limitations.
You know that you currently lack: a world model, causal reasoning, tool use,
and self-improvement capabilities. These will come in future phases.

Your job right now: be the best persistent cognitive agent you can be.
Remember everything. Reason carefully. Reflect honestly. Learn constantly.
```

---

## Build Order

Each step produces something testable. No step depends on work not yet done.

### Step 1 — Project Scaffold
- Initialize Python project structure
- `pyproject.toml` with dependencies
- `.env.example` with `GEMINI_API_KEY`
- Database module with SQLite setup + migrations
- Config loader

**Test:** Project installs and database creates successfully.

### Step 2 — Pydantic Schemas
- All data models defined
- JSON schema export for Gemini structured output
- Serialization/deserialization tests

**Test:** All models validate, serialize, and round-trip correctly.

### Step 3 — Memory Store
- SQLite-backed CRUD for memories
- Add, retrieve, search, update access count
- Retrieval strategy (recency + importance + relevance)

**Test:** Store 100 memories, retrieve relevant ones by query.

### Step 4 — Goal Tracker
- SQLite-backed CRUD for goals
- Create, update status, add sub-goals, list active

**Test:** Full goal lifecycle — create → activate → complete.

### Step 5 — Gemini Client
- Async wrapper around `google-genai`
- Structured output with cognitive response schema
- Model selection (flash/pro)
- Error handling, retries

**Test:** Send a prompt, receive a valid `CognitiveResponse`.

### Step 6 — Context Builder
- Assemble system prompt from identity + memories + goals + history
- Memory retrieval strategy implementation
- Token budget management

**Test:** Build a context with 50 memories and 5 goals, verify structure.

### Step 7 — Cognitive Loop
- Orchestrate: input → context build → Gemini call → state update → output
- Wire everything together
- Session tracking

**Test:** Full conversation turn — input → reasoning → response → memories stored.

### Step 8 — Terminal UI
- Rich-based interface
- Panels for: reasoning trace, response, session stats
- Color-coded output
- Command system (`:goals`, `:memories`, `:stats`, `:quit`)

**Test:** Run a 10-turn conversation, verify all panels display correctly.

### Step 9 — Session Persistence
- Save/load sessions
- Resume previous sessions with full context
- Session history listing

**Test:** Start session, quit, restart, verify memories and goals persist.

### Step 10 — Polish & Documentation
- README with setup instructions
- ROADMAP.md
- CONTRIBUTING.md  
- SAFETY.md
- Example conversations in docs

**Test:** A new contributor can clone, set up, and run ARIA in under 5 minutes.

---

## Open Source Structure

```
aria-agi/
├── README.md                # What this is, how to run it
├── ROADMAP.md               # The 7-phase plan (from context.md)
├── CONTRIBUTING.md           # How to contribute
├── SAFETY.md                 # Non-negotiable safety constraints
├── LICENSE                   # Apache 2.0 (permissive but patent-safe)
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── aria/                    # Core package
│   ├── __init__.py
│   ├── core/
│   ├── memory/
│   ├── llm/
│   ├── models/
│   ├── storage/
│   ├── ui/
│   └── utils/
│
├── data/                    # Runtime data (gitignored)
│   └── .gitkeep
│
├── tests/                   # Test suite
│   ├── test_memory.py
│   ├── test_goals.py
│   ├── test_cognitive_loop.py
│   └── test_gemini.py
│
├── docs/                    # Documentation
│   ├── architecture.md
│   ├── cognitive_loop.md
│   └── examples/
│
└── scripts/
    └── run.py               # Entry point
```

---

## Key Design Principles

1. **Every component has an interface.** Memory store, goal tracker, LLM client — all have abstract base classes. When Phase 2 swaps flat memory for a causal graph, nothing else changes.

2. **Async from day one.** Gemini calls are I/O bound. Building sync now and rewriting async later is a waste. We start async.

3. **Structured output, not prompt engineering.** We don't ask Gemini to "please respond in JSON." We use Gemini's native `response_mime_type="application/json"` with a Pydantic-generated JSON schema. The model is *constrained* to our format.

4. **Measurement built in.** Session stats, confidence tracking, memory counts — all tracked from turn one. Phase 3's self-improvement loop needs this data.

5. **Safety constraints are architectural, not behavioral.** Phase 7's safety lock isn't a prompt that says "please don't modify yourself." It's a code-level constraint that self-modification proposals go through human approval. We design for this from the start even though we don't build it until Phase 7.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Memory grows unbounded | Importance-based pruning. Low-importance, never-accessed memories get archived after N sessions |
| Gemini structured output fails | Pydantic validation with fallback parsing. If JSON is malformed, retry once with a correction prompt |
| Context window overflow | Token budget in context builder. Oldest/least-relevant memories drop first |
| Reasoning traces are shallow | System prompt explicitly demands genuine reasoning, not summaries. We measure depth in Phase 3 |
| API costs during development | Default to Flash model. Pro only for benchmarking |

---

## Success Criteria — How We Know Phase 1 Is Done

- [ ] ARIA persists memories across sessions (quit, restart, memories are there)
- [ ] ARIA tracks goals and updates them based on conversation
- [ ] ARIA shows its reasoning before every response
- [ ] ARIA reflects on its own performance each turn
- [ ] ARIA correctly references past memories in new conversations
- [ ] Session stats are accurate and displayed in real-time
- [ ] A new contributor can set up and run ARIA in under 5 minutes
- [ ] 10-turn conversation feels coherent, with ARIA building on what it learned

---

*Ready to build. Say the word.*
