# ARIA Phase 02 — World Model Implementation Plan

> **Problem it solves:** Understanding cause and effect, not just storing facts

---

## Why This Phase Matters

Phase 1 gave ARIA a flat memory bank — a list of facts. That's a database, not understanding. A world model is the difference between:

- **Phase 1:** "The user is building ARIA" (stored fact)
- **Phase 2:** "The user is building ARIA **because** they want AGI, **which requires** solving alignment, **which contradicts** moving fast" (causal understanding)

A world model means ARIA doesn't just know _what_ — it knows _why_ and _what follows from it_.

---

## Architecture: The Causal Entity Graph

### Core Concept

Every piece of knowledge becomes a **node** in a directed graph. Relationships between nodes are **typed edges** that express causality, dependency, contradiction, and association.

```
┌──────────┐     causes      ┌──────────────┐
│ Training │ ──────────────→ │ AI learns    │
│ data     │                 │ patterns     │
└──────────┘                 └──────┬───────┘
                                    │ enables
                                    ▼
┌──────────┐   contradicts   ┌──────────────┐
│ Overfit  │ ←─────────────  │ Generalize   │
│          │                 │ to new tasks │
└──────────┘                 └──────────────┘
```

### Edge Types

| Edge | Meaning | Example |
|------|---------|---------|
| `causes` | A produces B | "Data → learning" |
| `enables` | A makes B possible | "Memory → continuity" |
| `requires` | B depends on A | "AGI → alignment" |
| `contradicts` | A conflicts with B | "Speed → safety" |
| `supports` | A strengthens B | "Evidence → hypothesis" |
| `part_of` | A belongs to B | "Phase 1 → ARIA project" |
| `similar_to` | A resembles B | "ARIA → other agents" |
| `temporal` | A precedes B | "Phase 1 → Phase 2" |

### Node Schema

```python
class KnowledgeNode(BaseModel):
    """A node in ARIA's world model."""
    id: str
    content: str                    # The fact/concept
    node_type: str                  # "fact", "concept", "entity", "hypothesis", "principle"
    confidence: float               # How confident ARIA is in this node
    source: str                     # Where it came from
    created_at: str
    last_validated: str             # When this was last checked for truth
    validation_count: int           # How many times this was confirmed
    contradiction_count: int        # How many times this was challenged
    metadata: dict                  # Flexible extra data
```

### Edge Schema

```python
class CausalEdge(BaseModel):
    """A typed relationship between two knowledge nodes."""
    id: str
    source_node: str                # ID of the source node
    target_node: str                # ID of the target node
    edge_type: str                  # From the edge types table above
    strength: float                 # 0.0-1.0, how strong this relationship is
    evidence: str                   # Why this edge exists
    created_at: str
```

---

## Key Modules to Build

### 1. Knowledge Graph Engine (`aria/world/graph.py`)

The core graph data structure using NetworkX. Handles:

- **Add node** — Insert a fact/concept with typed metadata
- **Add edge** — Create a typed relationship between two nodes
- **Query subgraph** — Given a concept, return its causal neighborhood (what causes it, what it causes, what contradicts it)
- **Path finding** — Find causal chains between two concepts ("How does A eventually lead to B?")
- **Persistence** — Serialize/deserialize the graph to SQLite

> [!IMPORTANT]
> We use **NetworkX** (Python-native, in-memory) rather than Neo4j for Phase 2. The graph will be small enough that in-memory works fine, and it avoids requiring contributors to set up a separate database server. If the graph exceeds ~100K nodes in the future, we migrate to Neo4j.

### 2. Contradiction Detector (`aria/world/contradictions.py`)

When new information arrives that conflicts with existing beliefs:

1. **Detect** — Compare the new node against related nodes for logical conflicts
2. **Flag** — Create a "contradiction" edge between the conflicting nodes
3. **Reason** — Ask Gemini to evaluate which is more likely true, given the evidence
4. **Resolve** — Update confidence scores. The losing belief gets downgraded, not deleted. ARIA should be able to explain _why_ it changed its mind.

```
New info: "Scaling alone won't achieve AGI"
Existing: "Bigger models keep getting smarter"

ARIA detects contradiction → reasons about it → concludes:
  "Both are partially true. Scaling improves performance on existing
   tasks (confidence: 0.9) but may not produce genuine understanding
   (confidence: 0.7). These are different claims."
```

### 3. Hypothesis Engine (`aria/world/hypotheses.py`)

Given the causal graph, ARIA generates predictions:

1. **Inference** — Walk the graph to find implied conclusions. "If A causes B, and B enables C, then A may indirectly enable C."
2. **Prediction** — Generate testable hypotheses from the graph structure
3. **Verification** — When a prediction is confirmed or denied, update the graph edges and confidence scores

```
Graph: "User is interested in AGI" + "AGI requires alignment"
Hypothesis: "User is probably also interested in alignment"
Test: Ask the user. Update graph based on response.
```

> [!TIP]
> The hypothesis engine is what makes ARIA feel genuinely intelligent. A system that predicts things it was never told — and is right — demonstrates real understanding.

### 4. Graph Visualizer (`aria/world/visualizer.py`)

A terminal-based visualization of the causal graph using Rich:

- **Local view** — Show the neighborhood of a specific concept
- **Global summary** — High-level stats (nodes, edges, clusters, contradictions)
- **Contradiction map** — All active contradictions and their resolution status

Future option: Generate a proper graph visualization image using graphviz or pyvis for export.

### 5. Graph-Aware Context Builder (`aria/core/context_builder.py` — upgrade)

The Phase 1 context builder injects flat memories. Phase 2 upgrades this:

- **Graph traversal retrieval** — Instead of keyword matching, walk the graph outward from concepts in the user's message
- **Causal chains** — Include not just facts but their relationships ("X because Y, which means Z")
- **Active contradictions** — Surface unresolved contradictions relevant to the current topic
- **Pending hypotheses** — If ARIA has untested predictions about the topic, inject them

---

## Updated Cognitive Response Schema

Phase 2 extends the structured output from Gemini:

```python
class CognitiveResponse(BaseModel):
    # ... existing fields from Phase 1 ...

    # Phase 2 additions
    causal_observations: list[CausalObservation]  # New relationships detected
    contradictions_detected: list[Contradiction]   # Conflicts with existing knowledge
    hypotheses: list[Hypothesis]                   # Predictions to test
```

```python
class CausalObservation(BaseModel):
    """A causal relationship ARIA noticed in this turn."""
    from_concept: str
    to_concept: str
    relationship: str    # One of the edge types
    evidence: str        # Why ARIA believes this
    strength: float      # Confidence in this relationship

class Contradiction(BaseModel):
    """A conflict between new and existing knowledge."""
    new_claim: str
    existing_claim: str
    resolution: str      # ARIA's analysis of which is more likely
    confidence: float

class Hypothesis(BaseModel):
    """A prediction ARIA generates from its world model."""
    claim: str
    reasoning: str       # Why the graph implies this
    testable: bool       # Can this be verified?
    test_method: str     # How to verify (if testable)
```

---

## Storage: SQLite Schema Additions

```sql
-- Knowledge nodes (extends/replaces flat memories)
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'fact',
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'inference',
    created_at TEXT NOT NULL,
    last_validated TEXT NOT NULL,
    validation_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Causal edges
CREATE TABLE IF NOT EXISTS causal_edges (
    id TEXT PRIMARY KEY,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 0.5,
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_node) REFERENCES knowledge_nodes(id),
    FOREIGN KEY (target_node) REFERENCES knowledge_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON causal_edges(source_node);
CREATE INDEX IF NOT EXISTS idx_edges_target ON causal_edges(target_node);
CREATE INDEX IF NOT EXISTS idx_edges_type ON causal_edges(edge_type);

-- Hypotheses
CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    claim TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, confirmed, denied
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

-- Contradictions
CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY,
    node_a TEXT NOT NULL,
    node_b TEXT NOT NULL,
    analysis TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unresolved',  -- unresolved, resolved
    resolution TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (node_a) REFERENCES knowledge_nodes(id),
    FOREIGN KEY (node_b) REFERENCES knowledge_nodes(id)
);
```

---

## Migration Strategy: Memories → Knowledge Nodes

Phase 1 memories don't disappear. They get migrated:

1. Every existing `Memory` becomes a `KnowledgeNode` with `node_type = "fact"`
2. Tags become metadata
3. Importance scores carry over as confidence
4. The flat `related_memories` field gets expanded into actual `CausalEdge` entries
5. The old `memories` table is kept for backward compatibility but reads come from the graph

---

## New Terminal Commands

| Command | What it does |
|---------|-------------|
| `:graph` | Show graph summary (nodes, edges, clusters) |
| `:graph <concept>` | Show neighborhood of a specific concept |
| `:contradictions` | List all unresolved contradictions |
| `:hypotheses` | List pending hypotheses |
| `:why <concept>` | Show causal chain explaining a concept |

---

## Build Order

### Step 1 — Knowledge Node & Edge schemas
Pydantic models, SQLite tables, migration script for existing memories.

### Step 2 — NetworkX graph engine
Core graph operations: add/query/traverse/persist. Load from SQLite on startup, save on shutdown.

### Step 3 — Graph-aware context builder
Upgrade the context builder to walk the graph instead of flat keyword search.

### Step 4 — Extended Cognitive Response
Add causal observations, contradictions, and hypotheses to the Gemini structured output.

### Step 5 — Contradiction detector
Compare incoming knowledge against the graph, flag conflicts, ask Gemini to resolve.

### Step 6 — Hypothesis engine
Generate predictions from graph structure, track verification status.

### Step 7 — Graph visualizer
Terminal-based graph neighborhood display using Rich trees/tables.

### Step 8 — Updated identity prompt
Tell ARIA about its new capabilities — it now has a world model, can detect contradictions, and can make predictions.

---

## Success Criteria

- [ ] ARIA builds a causal graph from conversation (nodes + typed edges)
- [ ] ARIA detects contradictions between new and existing knowledge
- [ ] ARIA generates at least one hypothesis per 5 turns that is testable
- [ ] ARIA says "Based on what you told me about X, I predict Y" and is correct >50% of the time
- [ ] The `:graph` command shows a meaningful network of concepts
- [ ] The `:why` command traces a causal chain between two concepts
- [ ] Memory retrieval improves — graph traversal finds more relevant context than keyword search

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Graph grows explosively | Pruning: merge similar nodes, archive low-confidence edges after N sessions |
| Contradiction resolver always agrees with the latest info | Require explicit evidence comparison, not just recency |
| Hypotheses are trivial ("User likes coding") | Quality threshold — hypotheses must be non-obvious and testable |
| Graph traversal is slow | NetworkX handles ~100K nodes easily. Benchmark at 10K first |
| Gemini can't reliably extract causal relationships | Start with explicit edge types in the schema to constrain outputs |

---

## Dependencies

```
networkx>=3.0          # In-memory graph engine (already has no dependencies)
```

One new dependency. That's it.

---

*Phase 2 transforms ARIA from a database with a personality into a system that actually understands.*
