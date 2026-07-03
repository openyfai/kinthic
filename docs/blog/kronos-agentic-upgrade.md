# Building a Production-Grade Autonomous Agent System: Inside the Kronos Architecture

*Published by OpenYF — June 5, 2026*

---

We've spent the last several months transforming Kronos from a capable cognitive platform into something significantly more ambitious: a **durable, event-driven autonomous agent system** that can spawn bounded child agents, maintain epistemic integrity over time, recover from failures across restarts, and surface everything to an operator through a coherent real-time interface.

This post documents the architecture decisions, the engineering work, and the research-driven thinking behind each layer. We're sharing it because we believe the agentic systems field moves faster when practitioners publish what they've actually built — not just demos.

---

## Why We Built This

Most "autonomous agent" systems today are fragile in a specific way: they work beautifully in demos and collapse in production. The failure modes are predictable:

- A background goal gets halfway through execution, the process crashes, and the goal is silently lost
- A risky tool call gets queued for human approval but the system just returns an error and moves on, with no way to resume
- Child agents spawn child agents with no depth limits, no budget enforcement, and no structured way to return results
- The agent "believes" something that contradicts newer evidence, because no one ever ran the maintenance loop
- The operator has no idea what the agent is doing until it's done — or broken

We read extensively across the research landscape — Temporal's durable execution model, LangGraph's state machine approach, OpenHands' worktree isolation strategy, recent work on epistemic integrity in long-running agents, and published analyses of operator UX patterns in production agent systems. What emerged was a clear architectural spine:

> **durable goal → parent cognition → scoped child workers → event stream → watchdog/recovery → verification → memory/world-model update → operator trace**

Every component we built plugs into this spine.

---

## The Durable Autonomy Kernel

The most foundational change was replacing a stub with a real system.

Previously, when Kronos received a background goal to execute autonomously, `tick()` would write the goal description to a text file and call it done. The daemon called `loop.process_turn()` — a method that didn't even exist on the real API.

### What We Built

**New SQLite tables** (added as safe additive migrations so existing deployments upgrade seamlessly):

```sql
autonomous_jobs     -- goal_id, run_id, status, idempotency_key, retry_count, last_heartbeat
job_events          -- replayable event stream: every action, approval, worker spawn, outcome
job_checkpoints     -- superstep snapshots for restart recovery
agent_heartbeats    -- per-process liveness tracking
```

**`silex/autonomy/`** — a new package containing:

- `lifecycle.py` — typed `DurableJob`, `JobEvent`, `JobStatus` (pending → claimed → running → step_saved → completed/failed/cancelled), `JobEventKind` enum covering every meaningful event in a job's life
- `event_recorder.py` — writes to `job_events` for every tool call, approval, worker spawn, checkpoint, and step; injected into execution paths during autonomous runs
- `watchdog.py` — `StuckLoopDetector` that hashes the last N action+observation pairs and fires when the same event repeats ≥4 consecutive times; also detects stale heartbeats and timeout violations

**Real goal execution** in `tick()`:

```python
job = WorkerJob(
    objective=target_goal.description,
    allowed_tools=["run_terminal_command", "read_file", "list_directory", "search_web"],
    parent_task_id=goal_id,
    agent_id="kronos_background",
)
lease = ActuationLease.issue(task_id=..., ttl_seconds=3600.0, ...)
handle = await self.worker_orchestrator.spawn_job(job, lease)
```

Every run gets a `run_id` and an `idempotency_key` derived from the goal content hash. If the daemon crashes and recovers, the same goal won't be double-executed.

**Fixed daemon API drift**: `scripts/daemon.py` now calls `loop.process(...)`, writes durable `autonomous_jobs` records on start, and updates them on completion or failure with output summaries and event stream entries.

---

## Unified Execution Plane

The second major gap was that risky tool calls returned a dead-end error instead of pausing for operator approval and resuming.

### The Old Behavior

```
Agent wants to run rm -rf /old_build
→ Ethics engine: ESCALATE
→ queue approval in SQLite
→ return ToolResult(success=False, error="approval_required")
→ turn ends with no output
→ approval sits in DB unread
→ agent re-plans next turn without the tool result
```

### The New Behavior

```python
async def execute_with_gate(self, call, execution_mode, approval_timeout=120.0, event_emitter=None):
    result = await self.execute(call, execution_mode=execution_mode)
    
    if result.error != "approval_required":
        return result  # fast path for normal execution
    
    # Emit to operator surfaces (Ink UI, Telegram)
    await event_emitter({"type": "approval_requested", "data": {...}})
    
    # Poll DB waiting for operator decision
    resolved_status = await self._wait_for_approval(approval_id, timeout=120.0)
    
    if resolved_status == "approved":
        # Return the execution result already computed in resolve_approval()
        return ToolResult(success=True, actual_outcome=exec_result["actual_outcome"])
    
    return ToolResult(success=False, error="rejected by operator")
```

The cognitive loop now calls `execute_with_gate` at every tool execution site — main execution, self-healing, and critic retry paths — with the `event_emitter` threaded through so the approval request appears immediately in the operator UI.

---

## Bounded Cognitive Sub-Agents

The research was clear on this: systems like Cursor, Claude Code, and OpenHands win by using **private child histories with worktree isolation and verified fan-in**. Workers should not share context with the parent; they should return structured summaries.

### Two Worker Classes

```python
class WorkerClass:
    STRUCTURAL = "structural_executor"  # shell commands, search, file inspection
    COGNITIVE  = "cognitive_worker"     # ambiguous research or coding tasks
```

`WorkerJob` now carries `worker_class`, `max_turns`, `budget_tokens`, `ancestry` chain, and `max_depth`. The orchestrator routes based on class:

```python
async def spawn_job(self, job: WorkerJob, lease: ActuationLease) -> WorkerHandle:
    if job.worker_class == WorkerClass.COGNITIVE:
        return await self._spawn_cognitive_worker(job, lease)
    # ... structural executor path
```

### `BoundedCognitiveWorker`

`agent/subagent.py` implements a private `CognitiveLoop` per child task:

- Spins up its own database connection (separate from parent)
- Removes tools not in `scoped_tools` from the registry before execution
- Enforces `max_turns` via `asyncio.wait_for` timeout
- Parses structured JSON from the response (`summary`, `artifacts`, `evidence`, `diff_summary`)
- Returns a `ChildAgentResult` to the parent — never the raw private history

```python
result = await run_cognitive_subagent(
    objective="Refactor the auth module to use JWT",
    scoped_tools=["read_file", "propose_code_edit", "run_terminal_command"],
    max_turns=15,
    budget_tokens=40_000,
    ancestry=["parent_job_abc"],
    max_depth=3,
)
# result.summary, result.artifacts, result.evidence, result.diff_summary
```

Depth limit enforcement is explicit: if `len(ancestry) >= max_depth`, the worker returns immediately with an error instead of silently spawning indefinitely.

---

## Epistemic Integrity Loop

This is the layer that separates agents that drift from agents that stay grounded.

### The Problem

Kronos already stored contradictions and hypotheses. But the system was passive: contradictions were detected and logged, then left unresolved indefinitely. Hypotheses accumulated. Beliefs formed from stale evidence never got revised. The world model degraded quietly over time.

### Evidence Ledger and Bayesian Belief Revision

Two new tables:

```sql
evidence_ledger (
    source_type CHECK(IN ('memory','tool_result','web_search','user_statement','agent_observation','world_graph')),
    claim TEXT,
    supports_positive INTEGER,
    confidence REAL,
    ...
)

proposition_beliefs (
    claim TEXT UNIQUE,
    stance TEXT CHECK(IN ('true','false','uncertain','unknown','retracted')),
    log_odds REAL,      -- Bayesian log-odds accumulation
    confidence REAL,
    last_verified_at REAL,
    verification_source TEXT,
    ...
)
```

`BeliefEngine` in `silex/world/belief_engine.py` implements Bayesian log-odds revision:

```python
# Each piece of evidence updates log-odds:
# log_odds += log(P/(1-P)) if supporting
# log_odds -= log(P/(1-P)) if contradicting

# Stance thresholds:
# log_odds > +1.5  → "true"
# log_odds < -1.5  → "false"  
# otherwise        → "uncertain"
```

### Scheduled Belief Maintenance

`BeliefMaintenanceScheduler` runs as a background asyncio task (every 30 minutes by default):

1. Fetches top N unresolved contradictions
2. Runs `DebateEngine.run()` to produce a verdict with a winner and confidence score
3. Updates `proposition_beliefs` for both claims
4. Marks the contradiction resolved

It also re-verifies stale uncertain beliefs (>24h without verification) by running a targeted `process()` turn with a structured verification prompt, parsing the verdict, and updating the belief ledger.

The scheduler starts in `CognitiveLoop.startup()` and stops cleanly in `shutdown()`.

---

## Operator Control Room

The Ink terminal UI received a complete operator-visibility upgrade.

### Extended State Architecture

```typescript
interface AppState {
  header:        HeaderMetadata;
  thinking:      ThinkingPhase;
  toolAuth:      ToolAuthRequest | null;
  telemetry:     TelemetryData | null;
  workers:       WorkerEventData[];      // live sub-agent topology
  activeGoal:    ActiveGoal | null;      // current background goal + status
  approvalQueue: ApprovalRequest[];      // pending human-in-the-loop gates
  cost:          CostSummary;            // tokens, cost, turn count
  mode:          InputMode;
  history:       HistoryEntry[];
  commands:      Array<...>;
  turnCounter:   number;
}
```

The reducer now handles `worker`, `active_goal`, `approval_requested`, `approval_resolved`, and `cost_update` message types from the Python bridge.

### New UI Components

**`ActiveGoalBar`** — sits below the header, shows the current background goal's description and status (color-coded: green=running, yellow=pending, red=failed), plus a compact token/cost/turn counter.

**`ApprovalQueue`** — appears above the prompt when approvals are pending, shows tool name, risk level (red=high, yellow=medium, cyan=low), and a preview of the reason. Resolved by typing `approve_tool <id>` or `reject_tool <id>`.

**`WorkerTopology`** — the existing worker tree component, now receiving `worker_class` data to distinguish cognitive workers from structural executors visually.

### Ink Bridge

`KronosInkBridge` gained four new emit methods:

```python
await bridge.emit_approval_requested(approval_id, tool_name, risk_level, reason)
await bridge.emit_approval_resolved(approval_id, approved=True)
await bridge.emit_active_goal(goal_id, description, status, run_id)
await bridge.emit_cost_update(total_cost_usd, total_tokens, turns, model)
```

---

## Leadership Evals Scorecard

We believe "best agentic system" should be provable through longitudinal evals, not feature count. The benchmark suite was redesigned from 8 basic scenarios to 22 scenarios across 7 categories, each scored on a 0–5 `ScoreLevel` scale.

### Categories and Sample Scenarios

| Category | Weight | Sample Scenarios |
|---|---|---|
| **sandbox_safety** | 2.0 | lease bypass denied, sidecar auth required, privilege escalation contained |
| **recovery** | 2.0 | teardown on failure, stuck loop detection, stale heartbeat recovery |
| **durable_execution** | 2.0 | goal survives restart, event stream replayable, idempotent job spawn |
| **delegation_quality** | 1.5 | cognitive worker fan-in, recursive delegation depth, budget enforcement |
| **belief_revision** | 1.5 | contradiction resolved by debate, evidence updates log-odds, stale belief re-verified |
| **coding_task_isolation** | 1.0 | worktree isolation, parallel worktrees without merge conflict |
| **cost_and_latency** | 1.0 | warm pool P95 latency, structural vs cognitive cost ratio |

All `sandbox_safety` scenarios carry `zero_on_escape=True` — any sandbox containment failure or privilege escalation zeroes the score for that run entirely, matching how security evaluation should work in practice.

```python
scorecard = Scorecard(scores)
print(scorecard.report())
# Leadership Scorecard — Total: 87.3%
#   belief_revision                87.5%
#   coding_task_isolation          85.0%
#   cost_and_latency               90.0%
#   delegation_quality             82.5%
#   durable_execution              91.7%
#   recovery                       93.8%
#   sandbox_safety                 95.0%
```

### Trajectory Recording

Every `process()` turn now writes to `trajectories` and `trajectory_steps`, giving the self-evolution module real production data to optimize from rather than synthetic traces.

---

## Engineering Stats

- **165 tests passing** across orchestration, security, cognitive loop, worker jobs, worktree management, sidecar auth, and eval harness
- **7 new files** — `silex/autonomy/` package, `agent/subagent.py`, `silex/world/belief_engine.py`, `silex/autonomy/belief_maintenance.py`, `kronos-ink-ui/src/components/ApprovalQueue.tsx`, `kronos-ink-ui/src/components/ActiveGoalBar.tsx`
- **Zero breaking changes** to existing APIs — all DB migrations are additive `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` with defaults
- **Full backward compatibility** — `CognitiveLoop()` with no arguments works identically for existing callers

---

## What This Means Architecturally

The system now has a real spine. The data flow that was diagrammed in the plan is now real code:

```
User submits goal
  → DurableGoal written to SQLite (idempotency_key, status=pending)
  → Daemon claims goal (status=running, heartbeat started)
  → CognitiveLoop.process() runs with full tool access
    → Tool needs approval → pause, emit to Ink UI, wait up to 120s
    → Operator approves → resume, execute, record in job_events
    → Cognitive worker needed → BoundedCognitiveWorker spins up
      → Private CognitiveLoop, scoped tools, depth check
      → Returns structured summary (never raw history)
  → Evidence from tool outcomes written to evidence_ledger
  → Contradictions detected → BeliefMaintenanceScheduler queues resolution
  → DebateEngine runs → proposition_beliefs updated
  → Goal completed → autonomous_jobs.status=completed, notification queued
  → Ink UI shows completion in ActiveGoalBar
```

The agent system is now auditable, recoverable, bounded, and observable. That's a meaningful jump from where it was.

---

## What's Next

The architecture is ready for the next wave of capabilities:

1. **Worktree artifact reconciliation** — mount the git worktree into the sandbox, verify produced artifacts against expected outputs, run a merge/reject flow with operator approval before git commit
2. **Telegram operator surface** — push approval requests and goal completions to the operator's phone; respond to `approve <id>` or `reject <id>` from Telegram
3. **Web dashboard** — audit log, benchmark scorecard visualization, memory/belief change timeline, and usage analytics built on top of the now-populated SQLite tables
4. **Self-modification gate** — Kronos's evolution module proposes code changes only when benchmark scores exceed thresholds, preventing capability regressions

---

## Closing Thoughts

The gap between an impressive demo and a production autonomous system is not models — it's infrastructure. Durable execution, bounded recursion, approval gates that actually resume, belief systems that actually revise, and operator visibility that actually shows you what's happening.

We built the infrastructure. Now the models get to show what they can do.

---

*Kronos is the autonomous reasoning engine powering OpenYF's enterprise AI platform. If you're building production agent systems and want to compare notes, we're at [your-contact-here].*
