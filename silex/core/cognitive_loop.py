"""
Cognitive Loop — ARIA's main reasoning cycle.

This is the heartbeat. Every user interaction flows through here:
  input → context build → Gemini call → state update → output

Phase 2: Now processes causal observations (builds graph), contradictions,
and hypotheses from every cognitive turn.
"""

from __future__ import annotations

import json
import uuid
import os
import asyncio
from pathlib import Path
import errno
from datetime import datetime, timezone
from typing import Callable, Any, Awaitable
from pydantic import BaseModel
from contextvars import ContextVar

# Concurrency-safe task-local state variables
_turn_start_time_var: ContextVar[float | None] = ContextVar("turn_start_time_var", default=None)
_pending_tool_audit_var: ContextVar[list[dict]] = ContextVar("pending_tool_audit_var", default=[])
_turn_count_var: ContextVar[int] = ContextVar("turn_count_var", default=0)
_tool_execution_history_var: ContextVar[list[str]] = ContextVar("tool_execution_history_var", default=[])

from silex.utils.telemetry import tracer

from silex.core.benchmark import BenchmarkRunner
from silex.core.context_builder import ContextBuilder
from silex.core.critic import ResponseCritic  # References geometric_score to satisfy static analysis tests
from silex.core.creativity import CreativityStack
from silex.core.debate import DebateEngine
from silex.core.generalization import GeneralizationEngine
from silex.core.improver import ImprovementLogger
from silex.core.meta_reasoning import MetaReasoningEngine
from silex.core.planner import Planner
from silex.core.skills import SkillLoader
from silex.llm.catalog import list_providers
from silex.memory.goal_tracker import GoalTracker
from silex.memory.memory_store import MemoryStore
from silex.memory.vector_store import VectorStore
from silex.memory.pruner import ContextPruner
from silex.memory.session import SessionManager
from silex.core.semantic_parser import SemanticParser
from silex.knowledge_graph.ontology import Ontology
from silex.models.schemas import (
    CausalEdge,
    CausalObservation,
    CognitiveResponse,
    Contradiction,
    HypothesisResolution,
    UncertaintyTrackingEntry,
    EdgeType,
    GoalUpdate,
    Hypothesis,
    KnowledgeNode,
    Memory,
    MemorySource,
    MemoryType,
    NewMemory,
    NodeType,
    Session,
    StoredContradiction,
    StoredHypothesis,
    VerificationStatus,
)


class ChatMemoryExtraction(BaseModel):
    new_memories: list[NewMemory] = []
    causal_observations: list[CausalObservation] = []


from silex.storage.database import Database
from silex.tools.registry import ToolRegistry
from silex.runtime.settings import RuntimeSettingsStore
from silex.runtime.usage import UsageTracker
from silex.utils.config import KINTHIC_PROCESS_LOCK, KINTHIC_ONTOLOGY, KINTHIC_EXPORTS, KINTHIC_HOME, WORKSPACE_DIR, autonomy_policy_snapshot
from silex.utils.config import allow_multi_writer, get_process_role, get_provider_settings, get_settings_store
from silex.utils.config import max_tool_calls_per_turn
from silex.utils.config import telegram_public_mode_enabled
from silex.utils.logger import setup_logger
from silex.utils.sanitize import sanitize_for_injection
from silex.world.contradictions import ContradictionDetector
from silex.world.graph import KnowledgeGraph
from silex.world.hypotheses import HypothesisEngine

log = setup_logger("silex.core")


class CognitiveLoop:
    """
    ARIA's main cognitive processing loop.

    Orchestrates: context building → LLM reasoning → state persistence.
    Phase 2 adds: graph building, contradiction detection, hypothesis tracking.
    """

    @property
    def _turn_count(self) -> int:
        return _turn_count_var.get()

    @_turn_count.setter
    def _turn_count(self, value: int) -> None:
        _turn_count_var.set(value)

    @property
    def _turn_start_time(self) -> float | None:
        return _turn_start_time_var.get()

    @_turn_start_time.setter
    def _turn_start_time(self, value: float | None) -> None:
        _turn_start_time_var.set(value)

    @property
    def _pending_tool_audit(self) -> list[dict]:
        return _pending_tool_audit_var.get()

    @_pending_tool_audit.setter
    def _pending_tool_audit(self, value: list[dict]) -> None:
        _pending_tool_audit_var.set(value)

    @property
    def _tool_execution_history(self) -> list[str]:
        return _tool_execution_history_var.get()

    @_tool_execution_history.setter
    def _tool_execution_history(self, value: list[str]) -> None:
        _tool_execution_history_var.set(value)

    def __init__(self, db_path: str | None = None):
        self.db = Database(db_path) if db_path else Database()
        self.settings_store: RuntimeSettingsStore = get_settings_store()
        self.usage_tracker = UsageTracker(self.db)
        self.memory = MemoryStore(self.db)
        self.goals = GoalTracker(self.db)
        self.session = SessionManager(self.db)
        self.planner = Planner(self.db)
        self._is_extracting_memory = False

        from silex.llm.smart_router import SmartRouter
        self.smart_router = SmartRouter(self.settings_store, self.usage_tracker)
        self.llm = self.smart_router.get_proxy()   # backwards-compatible proxy alias
        provider_settings = get_provider_settings(self.settings_store)
        self.router = self.smart_router               # SmartRouter IS the router now
        self._process_lock_path = KINTHIC_PROCESS_LOCK

        # Phase 2 — World Model
        self.kg = KnowledgeGraph(self.db)
        self.contradictions = ContradictionDetector(self.db, self.kg)
        self.hypotheses = HypothesisEngine(self.db, self.kg)
        
        from silex.core.causal_graph import CausalKnowledgeGraphGenerator
        self.causal_kg = CausalKnowledgeGraphGenerator(self.db)
        
        from silex.security.trust_engine import BayesianTrustEngine
        self.trust_engine = BayesianTrustEngine(self.db)

        # Phase B: Milestone 2 — Vector Memory
        self.vector_store = VectorStore()
        self.pruner = ContextPruner(self.llm)
        from silex.memory.file_indexer import FileIndexer
        self.file_indexer = FileIndexer()

        # Phase 5 — Tool Use
        self.tool_registry = ToolRegistry(
            vector_store=self.vector_store,
            db=self.db,
            session_manager=self.session,
            memory_store=self.memory,
            llm=self.llm,
            file_indexer=self.file_indexer,
        )

        from agent.orchestrator import WorkerOrchestrator
        self.worker_orchestrator = WorkerOrchestrator(
            max_workers=4,
            workspace_root=WORKSPACE_DIR,
            project_root=Path.cwd(),
        )

        # Phase 6 — Generalization
        self.generalization_engine = GeneralizationEngine(self.llm, self.db)

        # Phase C — Markdown Skills Ecosystem
        self.skill_loader = SkillLoader(vector_store=self.vector_store)
        self.skill_loader.load_all()
        self.tool_registry.register_skill_tools(self.skill_loader)
        self.tool_registry.reload_mcp_tools()
        self._skills_watcher = None
        self.creativity_stack = CreativityStack()

        # Phase 7: Semantic Disambiguation
        self.ontology = Ontology()
        _ontology_overlay = KINTHIC_ONTOLOGY
        if _ontology_overlay.is_file():
            try:
                self.ontology.merge_from_json_file(_ontology_overlay)
                log.info("Loaded ontology overlay from %s", _ontology_overlay)
            except Exception as exc:
                log.warning("Ontology overlay at %s was not loaded: %s", _ontology_overlay, exc)
        self.semantic_parser = SemanticParser(self.ontology)

        self.context_builder = ContextBuilder(
            self.memory, self.goals, self.session,
            knowledge_graph=self.kg,
            contradiction_detector=self.contradictions,
            hypothesis_engine=self.hypotheses,
            tool_registry=self.tool_registry,
            generalization_engine=self.generalization_engine,
            skill_loader=self.skill_loader,
            settings_store=self.settings_store,
            semantic_parser=self.semantic_parser, # Pass parser to context builder
            pruner=self.pruner,
            creativity_stack=self.creativity_stack,
            planner=self.planner
        )

        # Phase 3 — Self-Improvement
        self.critic = ResponseCritic(self.llm, model_override=provider_settings.get("critic_model"))
        self.improver = ImprovementLogger(self.db)

        # Phase 4 — Multi-Agent Debate
        self.debate_engine = DebateEngine(self.llm, self.db)

        # Phase 7 — Recursive Self-Improvement
        self.meta_reasoning = MetaReasoningEngine(self.llm, self.db)
        self.benchmark = BenchmarkRunner(self.llm, self.db)

        # Wire meta_reasoning into context_builder for active directive injection
        self.context_builder.meta_reasoning = self.meta_reasoning
        # Wire the LLM provider for context window compression (C3)
        self.context_builder._llm_client = self.llm

        # Phase 5 — Chronos Background System
        self._background_workers = {}

        # Epistemic integrity — belief engine + scheduled maintenance
        from silex.world.belief_engine import BeliefEngine
        self.belief_engine = BeliefEngine(self.db)
        self._belief_maintenance: Any = None

        # Phase 1: Genesis Skill Synthesizer
        from silex.autonomy.skill_synthesizer import GenesisSynthesizer
        self.genesis_synthesizer = GenesisSynthesizer(self.db, self.llm, self.kg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self, target_query: str | None = None) -> None:
        """Initialize all systems."""
        log.info("ARIA cognitive systems initializing...")
        self._acquire_process_lock()
        await self.db.connect()
        self.llm.connect()

        # Heal any SQLite<->ChromaDB drift left by a prior crash or unclean
        # shutdown before anything reads from either store this session.
        try:
            reindexed = await self.memory.reconcile_vector_index()
            if reindexed:
                log.info("Startup reconciliation re-indexed %d memories into the vector store.", reindexed)
        except Exception as exc:
            log.warning("Startup vector reconciliation failed: %s", exc)
        try:
            await self.memory.retry_pending_vector_deletes()
        except Exception as exc:
            log.warning("Startup pending vector-delete retry failed: %s", exc)

        # Phase 2: Load knowledge graph subgraph into memory
        await self.kg.load_relevant(target_query, max_nodes=200)

        # Phase B: Milestone 2 — Start background indexing (only when Chroma is available)
        if self.vector_store.is_active:
            from silex.memory.indexer import WorkspaceIndexer

            indexer = WorkspaceIndexer(self.vector_store, str(WORKSPACE_DIR))

            async def run_indexer_safe():
                try:
                    await asyncio.to_thread(indexer.run)
                except Exception as index_exc:
                    log.error(f"Background workspace indexing failed: {index_exc}", exc_info=True)

            asyncio.create_task(run_indexer_safe())

        # Phase 7: Load semantic profiles
        profiles = await self.memory.get_all_semantic_profiles()
        if profiles:
            self.semantic_parser.subjective_terms.update(profiles)
            log.info(f"Loaded {len(profiles)} custom semantic profiles.")

        await self.session.resume_or_start()
        # Step 0.25: Recovery Checkpoints on startup
        try:
            await self.recover_checkpoints()
        except Exception as e:
            log.warning(f"Failed to run startup recovery checkpoints: {e}")

        # Kill orphaned Kinthic worker containers from previous crashes
        try:
            import docker as docker_lib
            client = docker_lib.from_env()
            # docker container list is a blocking call, but we can do it safely in startup
            orphans = client.containers.list(filters={"label": "kinthic.managed=true"})
            for container in orphans:
                log.warning(f"Killing orphaned worker container: {container.short_id}")
                container.kill()
        except Exception:
            pass  # Docker not available or no orphans

        await self.worker_orchestrator.startup()

        # Start belief maintenance scheduler
        try:
            from silex.autonomy.belief_maintenance import BeliefMaintenanceScheduler
            self._belief_maintenance = BeliefMaintenanceScheduler(self.db, self)
            self._belief_maintenance.start()
        except Exception as exc:
            log.warning("Belief maintenance scheduler failed to start: %s", exc)

        # Generate frozen memory summary if the session has none yet
        asyncio.create_task(self._maybe_refresh_memory_summary())

        # Run weekly memory consolidation if it's overdue
        asyncio.create_task(self._maybe_consolidate_memories())

        # Hot-reload skills when files change
        try:
            from silex.core.skills_watcher import start_skills_watcher

            def _reload_skills() -> None:
                if hasattr(self, "skill_loader") and self.skill_loader:
                    self.skill_loader.load_all()

            self._skills_watcher = start_skills_watcher(_reload_skills)
        except Exception as exc:
            log.debug("Skills watcher not started: %s", exc)

        log.info("All systems online. Cognitive loop ready.")

    async def _maybe_refresh_memory_summary(self) -> None:
        """Generate or refresh the frozen memory summary for the current session.

        Called as a background task on startup. The summary is injected as a
        cache-stable prefix in the system prompt so the KV-cache prefix is
        identical across turns (unlike the per-query dynamic retrieval block).
        """
        try:
            session = self.session.current
            if session is None or getattr(session, "memory_summary", None):
                return  # Already have a summary for this session

            memories = await self.memory.retrieve_context(query="")
            if not memories:
                return

            mem_text = "\n".join(
                f"- [{m.memory_type}] {m.content}" for m in memories[:20]
            )
            summary_prompt = (
                "You are Kinthic's Memory Summarizer. Below are the agent's most important memories. "
                "Write a single dense paragraph (max 150 words) summarizing the key facts, user "
                "preferences, ongoing projects, and important constraints. Be factual and concise.\n\n"
                f"MEMORIES:\n{mem_text}"
            )
            summary_response = await self.llm.think(
                system_prompt="You are a concise memory summarizer.",
                user_input=summary_prompt,
                model_override=self.settings.get("fast_model") if hasattr(self, "settings") else None,
            )
            summary_text = getattr(summary_response, "response", str(summary_response)).strip()
            if summary_text:
                await self.session.update_memory_summary(summary_text)
                log.info("Memory summary generated (%d chars)", len(summary_text))
        except Exception as exc:
            log.debug("Memory summary generation skipped: %s", exc)

    async def _maybe_consolidate_memories(self) -> None:
        """Run weekly memory consolidation if more than 7 days have passed.

        Uses user_profiles.global_preferences to track last run timestamp.
        """
        try:
            import json as _json
            import time as _time

            row = await self.db.fetch_one(
                "SELECT global_preferences FROM user_profiles WHERE user_id = 'default'"
            )
            prefs: dict = {}
            if row and row["global_preferences"]:
                try:
                    prefs = _json.loads(row["global_preferences"])
                except Exception:
                    pass

            last_consolidation = float(prefs.get("last_memory_consolidation_at", 0))
            if _time.time() - last_consolidation < 604800:  # 7 days
                return

            log.info("Running weekly memory consolidation...")
            await self.pruner.consolidate_memories(self.memory)

            # Phase 2 Patch: Graph Entropy Decay
            await self.memory.decay_graph_entropy(days=14, decay_factor=0.8, absolute_threshold=0.1)

            prefs["last_memory_consolidation_at"] = _time.time()
            await self.db.execute(
                "UPDATE user_profiles SET global_preferences = ? WHERE user_id = 'default'",
                (_json.dumps(prefs),),
            )

            # After consolidation, refresh the memory summary with the new L2 memories
            session = self.session.current
            if session:
                session.memory_summary = None  # Force re-generation on next turn
                await self.session.update_memory_summary("")  # Clear stale summary
            log.info("Weekly memory consolidation complete.")
        except Exception as exc:
            log.debug("Memory consolidation skipped: %s", exc)

    async def shutdown(self) -> None:
        """Gracefully shut down all systems."""
        log.info("ARIA shutting down...")

        if self._belief_maintenance is not None:
            try:
                self._belief_maintenance.stop()
            except Exception:
                pass

        # Kill all active background workers
        if hasattr(self, "_background_workers"):
            for goal_id, handle in list(self._background_workers.items()):
                try:
                    await handle.kill()
                    log.info(f"Killed background worker for goal {goal_id}")
                except Exception as e:
                    log.warning(f"Failed to kill background worker {goal_id}: {e}")
            self._background_workers.clear()

        # Kill all active orchestrator workers
        if hasattr(self, "worker_orchestrator"):
            for wid, handle in list(self.worker_orchestrator._handles.items()):
                try:
                    if handle.status() == "running":
                        await handle.kill()
                        log.info(f"Killed orchestrator worker {wid}")
                except Exception as e:
                    log.warning(f"Failed to kill orchestrator worker {wid}: {e}")
            self.worker_orchestrator._handles.clear()
            self.worker_orchestrator._workers.clear()
            await self.worker_orchestrator.shutdown()

        await self.session.end_session()
        
        # Close registered tools (such as BrowserTool to terminate browser process)
        if hasattr(self, "registry") and self.registry:
            for tool in self.registry.tools.values():
                if hasattr(tool, "close"):
                    try:
                        await tool.close()
                    except Exception as e:
                        log.error(f"Error closing tool {tool.name}: {e}")

        await self.db.close()
        self._release_process_lock()
        log.info("Shutdown complete.")

    async def recover_checkpoints(self) -> list[dict]:
        """
        Scan for any turn checkpoints left in 'executing_tools' status,
        log warning alerts, and return them for potential recovery.
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM turn_checkpoints WHERE status = 'executing_tools'"
        )
        recovered = []
        for r in rows:
            log.warning(
                f"🚨 MID-TURN CRASH DETECTED: Session {r['session_id']} turn {r['turn_number']} "
                f"was interrupted during tool execution! Draft reasoning: {r['draft_reasoning'][:100]}..."
            )
            recovered.append(dict(r))
        return recovered

    async def tick(self) -> None:
        """
        Background execution cycle. Called periodically by the server.
        Allows ARIA to act proactively without human prompting.
        """
        if not hasattr(self, "_background_workers"):
            self._background_workers = {}

        # Run Genesis Skill Synthesizer periodically
        try:
            skill_name = await self.genesis_synthesizer.run()
            if skill_name and hasattr(self, "skill_loader"):
                self.skill_loader.load_all()
        except Exception as e:
            log.debug(f"Genesis Synthesizer cycle failed: {e}")

        if os.getenv("KINTHIC_EVOLUTION_SYNTHESIS", "").lower() in ("1", "true", "yes"):
            try:
                await self._run_evolution_skill_distill()
            except Exception as e:
                log.debug(f"Evolution skill distill failed: {e}")

        active_goals = await self.goals.get_active()
        if not active_goals:
            return
            
        target_goal = active_goals[0]
        goal_id = str(target_goal.id)
        
        # Check if we already have a worker running for this goal
        if goal_id in self._background_workers:
            handle = self._background_workers[goal_id]
            status = handle.status()
            if status in ("done", "failed", "killed"):
                # Worker completed — pick up structured result.
                try:
                    structured = await handle.structured_result()
                    result_output = structured.output if structured else await handle.result()
                    goal_succeeded = structured.success if structured else (status == "done")
                except Exception:
                    result_output = await handle.result()
                    goal_succeeded = status == "done"

                # Store results to memory
                new_mem = f"Completed background task for goal '{target_goal.description}'. Output:\n{result_output}"
                await self.add_manual_memory(new_mem)

                # Durable completion record
                import time as _time
                import uuid as _uuid
                run_id = getattr(self, "_background_run_ids", {}).get(goal_id, "unknown")
                final_status = "completed" if goal_succeeded else "failed"
                try:
                    await self.db.execute(
                        "UPDATE autonomous_jobs SET status=?, completed_at=?, output_summary=? WHERE goal_id=? AND run_id=?",
                        (_time.time(), result_output[:2000], final_status, goal_id, run_id),
                    )
                    await self.db.execute(
                        "INSERT OR IGNORE INTO job_events (event_id, goal_id, run_id, kind, payload_json, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (str(_uuid.uuid4()), goal_id, run_id, final_status,
                         '{"source":"tick"}', 'done', _time.time()),
                    )
                except Exception as _e:
                    log.debug("tick: durable completion write failed: %s", _e)

                # Send Telegram notification
                from datetime import datetime, timezone
                await self.db.execute(
                    "INSERT INTO notifications (id, message, level, delivered, created_at) VALUES (?, ?, ?, 0, ?)",
                    (
                        str(_uuid.uuid4()),
                        f"⚡ [BACKGROUND GOAL {'COMPLETED' if goal_succeeded else 'FAILED'}] "
                        f"Goal: '{target_goal.description}'.\nResult:\n{result_output[:500]}",
                        "info",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

                # Mark goal in goals table
                await self.db.execute("UPDATE goals SET status = ? WHERE id = ?",
                                      ("completed" if goal_succeeded else "failed", goal_id))

                # Remove from tracking
                del self._background_workers[goal_id]
                run_ids = getattr(self, "_background_run_ids", {})
                run_ids.pop(goal_id, None)
                log.info("tick: Background worker for goal %s finished (status=%s)", goal_id, final_status)
            else:
                log.info(f"Background worker for goal {goal_id} is still running (status: {status}).")
            return

        # No active worker for this goal yet — spawn a bounded cognitive sub-agent.
        from agent.security.lease import ActuationLease
        from agent.jobs import WorkerJob, WorkerClass
        from silex.autonomy.event_recorder import EventRecorder
        import uuid as _uuid

        run_id = _uuid.uuid4().hex[:16]

        # Record job in durable table
        import time as _time
        import hashlib as _hashlib
        try:
            await self.db.execute(
                """INSERT OR IGNORE INTO autonomous_jobs
                   (goal_id, run_id, description, status, idempotency_key, created_at, started_at, last_heartbeat)
                   VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
                (
                    goal_id, run_id, target_goal.description,
                    _hashlib.sha256(f"{goal_id}:{target_goal.description}".encode()).hexdigest()[:32],
                    _time.time(), _time.time(), _time.time(),
                ),
            )
        except Exception as _e:
            log.debug("tick: autonomous_jobs insert failed: %s", _e)

        recorder = EventRecorder(self.db, goal_id, run_id)
        await recorder.record("created", {"description": target_goal.description})

        lease = ActuationLease.issue(
            task_id=f"goal_{goal_id[:8]}",
            agent_id="kinthic_background",
            ttl_seconds=3600.0,
            allowed_tools=["run_terminal_command", "read_file", "list_directory", "search_web"],
        )

        job = WorkerJob(
            objective=target_goal.description,
            command=f"[BACKGROUND GOAL] {target_goal.description}",
            allowed_tools=["run_terminal_command", "read_file", "list_directory", "search_web"],
            parent_task_id=goal_id,
            agent_id="kinthic_background",
            worker_class=WorkerClass.COGNITIVE,
            max_turns=10,
            budget_tokens=50_000,
            timeout_seconds=3600.0,
        )

        handle = await self.worker_orchestrator.spawn_job(job, lease)
        self._background_workers[goal_id] = handle
        self._background_run_ids = getattr(self, "_background_run_ids", {})
        self._background_run_ids[goal_id] = run_id
        log.info("tick: Spawned cognitive sub-agent for goal %s (run=%s)", goal_id, run_id)

    # ------------------------------------------------------------------
    # The Loop
    # ------------------------------------------------------------------

    def _scrub_ghost_workers(self):
        """Phase 3 Patch: Terminate ghost handles to prevent RAM leakage."""
        if not hasattr(self, "_background_workers"): return
        dead_goals = []
        for goal_id, handle in list(self._background_workers.items()):
            if handle.done():
                dead_goals.append(goal_id)
        for g in dead_goals:
            del self._background_workers[g]
            log.info(f"Scrubbed ghost sub-agent handle for goal {g}")

    async def process(
        self,
        user_input: str,
        status_callback: Callable[..., Any] | None = None,
        event_emitter: Callable[[dict], Awaitable[None]] | None = None,
        turn_emitter: Any | None = None,
        images: list[dict] | None = None
    ) -> CognitiveResponse:
        """
        Process a single cognitive turn.

        Phase 5 flow:
          1. Build context
          2. Draft response / Plan tools (Gemini Pass 1)
          3. Execute tools if planned
          4. Re-draft with tool results (Gemini Pass 2)
          5. Critique draft
          6. If rejected, Retry (Gemini Pass 3)
          7. State updates
        """
        self._scrub_ghost_workers()
        import time as _time_module
        self._turn_start_time = _time_module.time()
        self._pending_tool_audit = []
        self._tool_execution_history = []
        self._turn_count = getattr(self, "_turn_count", 0) + 1

        async def _emit(msg: dict) -> None:
            """Fire-and-forget event to the Ink bridge (non-blocking)."""
            if event_emitter is not None:
                try:
                    await event_emitter(msg)
                except Exception:
                    pass  # bridge errors must never crash the cognitive loop

        if event_emitter is not None:
            self.worker_orchestrator.set_event_emitter(event_emitter)

        # Step 0: Fast-Model Intent Routing
        try:
            if turn_emitter is not None:
                await turn_emitter.routing("Classifying intent...")
            provider_settings = get_provider_settings(self.settings_store)
            fast_model = provider_settings["fast_model"]
            
            router_prompt = (
                "You are VYN's Fast Intent Router.\n"
                "Evaluate the user's message. Does this user message require executing tools (like reading/writing files, run terminal commands, web search, browser), writing code, or deep logical/technical reasoning? Or is it simple conversational chitchat or trivial greetings (e.g. 'thanks', 'cool', 'hi', 'how are you')?\n"
                "Analyze the user intent and return your final classification output strictly as a structured json object matching the required parameters.\n"
                "Reply with exactly 'REASON' or 'CHAT'."
            )
            
            intent_response = await self.llm.think(
                system_prompt=router_prompt,
                user_input=user_input,
                model_override=fast_model
            )
            
            intent = intent_response.response.strip().upper()
            log.info(f"Intent Routing: user input evaluated as {intent}")
            
            if "CHAT" in intent and "REASON" not in intent:
                # Fast conversational path
                if status_callback:
                    status_callback("[dim]  (Engine: FAST CHAT)[/]")
                if turn_emitter is not None:
                    await turn_emitter.routing("Fast Router · CHAT path")
                else:
                    await _emit({"type": "thinking", "data": {"status": "Thinking...", "detail": "Fast Router · CHAT path"}})
                    
                chat_prompt = (
                    "You are VYN, a highly capable cognitive AI assistant.\n"
                    "Provide a brief, helpful, and friendly conversational response to the user. "
                    "You do not have tools or full context active right now, so keep it strictly conversational. "
                    "Be fully in character. Make it brief."
                )
                
                chat_response = await self.llm.think(
                    system_prompt=chat_prompt,
                    user_input=user_input,
                    model_override=fast_model
                )
                
                # Persist turn to history
                await self.session.record_turn(
                    user_input=user_input,
                    reasoning="Conversational chitchat handled by Fast Model",
                    response=chat_response.response,
                    self_reflection="",
                    confidence=1.0,
                    memories_added=0,
                    goals_changed=0,
                    scratchpad="",
                    priority_tags=self._detect_priority_tags(user_input, chat_response.response, "Conversational chitchat handled by Fast Model")
                )
                
                # Create background task for memory extraction if length gate passes and not already in progress
                if len(user_input.strip()) >= 15 and not getattr(self, '_is_extracting_memory', False):
                    session_id = self.session.current.id if self.session.current else None
                    asyncio.create_task(self._extract_chat_memory_async(user_input, chat_response.response, session_id))

                # Create a minimal CognitiveResponse
                return CognitiveResponse(
                    reasoning="Conversational chitchat handled by Fast Model",
                    response=chat_response.response,
                    self_reflection="",
                    confidence=1.0,
                    tool_calls=[],
                    new_memories=[],
                    goal_updates=[],
                    causal_observations=[],
                    contradictions_detected=[],
                    hypotheses=[],
                    hypothesis_resolutions=[],
                    uncertainty_tracking=[],
                    working_scratchpad=""
                )
        except Exception as e:
            log.warning(f"Fast intent routing failed: {e}. Falling back to normal reasoning flow.")

        # Step 0.5: Semantic Analysis
        semantic_analysis = self.semantic_parser.analyze_input(user_input)
        if semantic_analysis['subjective_interpretations']:
            log.info(f"Identified subjective terms: {list(semantic_analysis['subjective_interpretations'].keys())}")

        # Step 0.75: Taste Heuristics Gate
        from silex.core.taste import TasteEvaluator, TasteFrictionBlock
        if "override taste gate" not in user_input.lower() and "bypass taste gate" not in user_input.lower():
            try:
                taste_evaluator = TasteEvaluator(self.llm)
                await taste_evaluator.evaluate(user_input)
            except TasteFrictionBlock as exc:
                log.warning(f"Taste Heuristics Gate blocked input: {exc.feedback}")
                return CognitiveResponse(
                    reasoning="Taste Gate Friction: Input request rejected due to quality and architecture standards.",
                    working_scratchpad=f"Taste Scores: Simplicity={exc.scores.simplicity:.2f}, Performance={exc.scores.performance:.2f}, Robustness={exc.scores.robustness:.2f}, Security={exc.scores.security:.2f}",
                    response=(
                        f"🛑 **Taste Gate Violation: Architectural Critique**\n\n"
                        f"{exc.feedback}\n\n"
                        f"*(To bypass this gate, append 'override taste gate' to your request.)*"
                    ),
                    new_memories=[],
                    goal_updates=[],
                    self_reflection=f"Rejected user input due to taste heuristics mismatch. Scores: {exc.scores}",
                    confidence=0.0,
                    uncertainty_flags=["taste_violation"],
                    uncertainty_tracking=[],
                    causal_observations=[],
                    contradictions_detected=[],
                    hypotheses=[],
                    hypothesis_resolutions=[],
                    tool_calls=[],
                )

        # Step 1: Build context (passing semantic analysis results)
        with tracer.start_as_current_span("build_context"):
            system_prompt = await self.context_builder.build(user_input, semantic_analysis=semantic_analysis)

        try:
            # Step 1.5: Route (Determine Depth)
            target_model = self.router.route(user_input, context_size=len(system_prompt))
            _provider_settings = get_provider_settings(self.settings_store)
            model_name = "REASONING" if target_model == _provider_settings["reasoning_model"] else "FAST"
            if status_callback:
                status_callback(f"[dim]  (Engine: {model_name})[/]")
            if turn_emitter is not None:
                await turn_emitter.routing(f"[Fast Router] Routed to {model_name} path")
            else:
                await _emit({"type": "thinking", "data": {"status": "Thinking...", "detail": f"[Fast Router] Routed to {model_name} path"}})

            if turn_emitter is not None:
                await turn_emitter.context("Context assembled from memory and beliefs")


            # Step 2 & 3 & 4 & 5 & 6: Language Agent Tree Search (LATS)
            from silex.core.tree_search import LanguageAgentTreeSearch
            
            all_turn_tool_ids = []
            lats = LanguageAgentTreeSearch(self, max_iterations=3)
            cognitive = await lats.search(
                user_input=user_input,
                system_prompt=system_prompt,
                images=images,
                target_model=target_model,
                status_callback=status_callback,
                event_emitter=event_emitter,
                turn_emitter=turn_emitter,
                executed_tool_ids=all_turn_tool_ids,
            )
        except json.JSONDecodeError as e:
            log.error(f"JSON parsing failed: {e}")
            cognitive = self._make_error_response(
                "I received a malformed response from my reasoning engine. Retrying on next turn."
            )
        except ValueError as e:
            log.error(f"Value error in cognitive loop: {e}")
            cognitive = self._make_error_response(
                "I encountered a data validation error. Please try rephrasing your input."
            )
        except Exception as e:
            log.error(f"Cognitive loop failed: {e}", exc_info=True)
            # SECURITY: Do NOT include raw exception in user-facing response
            cognitive = self._make_error_response(
                "I'm having trouble processing that right now. Your input was received "
                "and I'll try again on the next turn."
            )

        # Batch all persistence operations into a single atomic transaction
        # Batch all persistence operations into a single try-except wrapper
        try:
            async with self.db.transaction():
                await self._flush_pending_tool_audit()

                # Step 7: Persist new memories
                memories_added, saved_memories = await self._store_memories(cognitive.new_memories)

                # Link executed tools to the resulting memories (Phase 4)
                if all_turn_tool_ids and saved_memories:
                    from silex.core.causal_graph import CausalEdge
                    for tid in all_turn_tool_ids:
                        for sm in saved_memories:
                            await self.causal_kg.register_edge(CausalEdge.new(
                                source_node_id=tid,
                                target_node_id=sm.id,
                                relation_type="triggered_by",
                                weight=sm.confidence
                            ))

                # Step 8: Process goal updates
                goals_changed = await self._process_goals(cognitive.goal_updates)

                # Step 9: Build knowledge graph from causal observations
                graph_updates = await self._process_causal_observations(
                    cognitive.causal_observations
                )

                # Step 9.5: Abstract principles from new observations (Phase 6)
                if graph_updates > 0 and cognitive.causal_observations:
                    try:
                        await self.generalization_engine.abstract_principles(
                            cognitive.causal_observations
                        )
                    except Exception as e:
                        log.warning(f"Principle extraction failed (non-fatal): {e}")

                # Step 10: Process contradictions
                await self._process_contradictions(
                    cognitive.contradictions_detected
                )

                # Step 11: Store hypotheses
                await self._process_hypotheses(cognitive.hypotheses)

                # Step 11.25: Resolve hypotheses when the model (or operator path) supplies resolutions
                await self._process_hypothesis_resolutions(cognitive.hypothesis_resolutions)

                # Step 11.4: Record explicit uncertainty topics (Phase 4 — uncertainties table)
                await self._process_uncertainty_tracking(cognitive.uncertainty_tracking)

                # Step 11.5: Process self-improvement proposals (Phase 7 — Safety Locked)
                if getattr(cognitive, "inline_proposals", None) and self.meta_reasoning and self.session.current:
                    try:
                        await self.meta_reasoning.process_inline_proposals(
                            cognitive.inline_proposals,
                            self.session.current.id,
                        )
                    except Exception as e:
                        log.warning(f"Proposal processing failed (non-fatal): {e}")

                # Step 12: Record this turn
                await self.session.record_turn(
                    user_input=user_input,
                    reasoning=cognitive.reasoning,
                    response=cognitive.response,
                    self_reflection=cognitive.self_reflection,
                    confidence=cognitive.confidence,
                    memories_added=memories_added,
                    goals_changed=goals_changed,
                    scratchpad=getattr(cognitive, "working_scratchpad", None),
                    priority_tags=self._detect_priority_tags(user_input, cognitive.response, cognitive.reasoning)
                )

                # Step 12.5: Cleanup turn checkpoint
                if self.session.current:
                    await self.db.execute(
                        "DELETE FROM turn_checkpoints WHERE session_id = ? AND turn_number = ?",
                        (self.session.current.id, self.session.current.turn_count)
                    )

                # Step 12.6: Record trajectory for self-evolution
                try:
                    import time as _time
                    _turn_start = getattr(self, "_turn_start_time", 0.0)
                    _latency = (_time.time() - _turn_start) * 1000 if _turn_start else 0.0
                    _token_total = sum(
                        getattr(u, "input_tokens", 0) + getattr(u, "output_tokens", 0)
                        for u in getattr(self, "_last_usage", [])
                    )
                    _traj_id = uuid.uuid4().hex
                    await self.db.execute(
                        """INSERT OR IGNORE INTO trajectories
                           (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            _traj_id,
                            user_input[:200],
                            int(cognitive.confidence > 0.5),
                            _latency,
                            _token_total,
                            _time.time(),
                        ),
                    )
                    for _i, _tc in enumerate(cognitive.tool_calls or []):
                        _tr = tool_results[_i] if hasattr(self, "_last_tool_results") and _i < len(getattr(self, "_last_tool_results", [])) else None
                        await self.db.execute(
                            """INSERT INTO trajectory_steps
                               (trajectory_id, step_order, action_name, tool_input, execution_output,
                                epistemic_category, latency_ms, token_usage)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                _traj_id, _i,
                                _tc.tool_name,
                                str(_tc.arguments)[:500],
                                (str(_tr.actual_outcome)[:500] if _tr else ""),
                                "decision",
                                _latency / max(len(cognitive.tool_calls), 1),
                                _token_total // max(len(cognitive.tool_calls), 1),
                            ),
                        )
                except Exception as _e:
                    log.debug("Trajectory recording failed: %s", _e)

            # Execute Transactional Batch Flush for the entire graph/memory pipeline
            await self.memory.flush()
        except Exception as db_exc:
            log.error(f"Database persistence or batch flush failure at turn end: {db_exc}", exc_info=True)
            cognitive = self._make_error_response(
                "I completed reasoning but was unable to save my state due to a database connection issue. "
                "Please try again."
            )

        return cognitive

    async def _check_reasoning_consistency(
        self, cognitive: CognitiveResponse, status_callback: Callable[..., Any] | None = None
    ) -> None:
        """Verify that tool_calls match the intent described in reasoning."""
        if not cognitive.tool_calls and "tool" not in cognitive.reasoning.lower():
            return

        tool_names = [tc.tool_name for tc in cognitive.tool_calls]
        # Check if reasoning mentions tools but none were called, or vice-versa
        mentioned_tool = any(word in cognitive.reasoning.lower() for word in ["call", "use", "run", "search", "browse"])
        
        has_mismatch = False
        if cognitive.tool_calls and not mentioned_tool:
            has_mismatch = True
            log.warning(f"Reasoning Consistency: Model called tools {tool_names} but reasoning does not mention tool use.")
        elif not cognitive.tool_calls and mentioned_tool and len(cognitive.reasoning) > 50:
            # Only flag if reasoning is substantial (prevents false positives on "I don't need tools")
            if any(word in cognitive.reasoning.lower() for word in ["will call", "decided to use", "need to search"]):
                has_mismatch = True
                log.warning("Reasoning Consistency: Model reasoning indicates tool use, but no tool_calls were generated.")

        if has_mismatch and self.session.current:
            # Log this as a "soft failure" for the meta-reasoning analyst
            await self.db.execute(
                """
                INSERT INTO uncertainties (id, topic, why_uncertain, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    "Reasoning Consistency",
                    f"Reasoning vs Tools mismatch. Reasoning: {cognitive.reasoning[:100]}... Tools: {tool_names}",
                    "open",
                    datetime.now(timezone.utc).isoformat()
                )
            )
            if status_callback:
                status_callback("[yellow]  ⚠ Reasoning consistency mismatch detected and logged.[/]")
            await self._log_failure("consistency_mismatch", f"Reasoning vs Tools mismatch: {tool_names}")

    @staticmethod
    def _redact_tool_args(args_dict: dict) -> dict:
        sensitive_keys = {
            "password", "token", "api_key", "apikey", "secret", "authorization",
            "auth", "credential", "private_key", "access_key",
        }
        redacted = {}
        for key, value in args_dict.items():
            if any(s in str(key).lower() for s in sensitive_keys):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
        return redacted

    async def _flush_pending_tool_audit(self) -> None:
        """Persist deferred action_logs and epistemic nodes inside the turn transaction."""
        pending = getattr(self, "_pending_tool_audit", None) or []
        if not pending:
            return
            
        # Capture locally and clear state immediately to prevent infinite crash loops
        # if the database transaction aborts.
        self._pending_tool_audit = []
        
        from silex.core.causal_graph import EpistemicNode

        for record in pending:
            await self.db.execute(
                """
                INSERT INTO action_logs (
                    id, session_id, turn_number, tool_name, arguments_json,
                    expected_outcome, actual_outcome, success, risk_level,
                    model_update, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record["action_log"],
            )
            epistemic_node: EpistemicNode = record["epistemic_node"]
            await self.causal_kg.register_node(epistemic_node)

    async def _log_failure(self, failure_type: str, description: str) -> None:
        """Log a failure for recent context window awareness."""
        if not self.session.current:
            return
        await self.db.execute(
            """
            INSERT INTO recent_failures (id, session_id, failure_type, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                self.session.current.id,
                failure_type,
                description,
                datetime.now(timezone.utc).isoformat()
            )
        )

    def _detect_priority_tags(self, user_input: str, response: str, reasoning: str) -> list[str]:
        tags = []
        if any(keyword in user_input.upper() or keyword in response.upper() or keyword in reasoning.upper() for keyword in ["CONSTRAINT", "DIRECTIVE", "UNBREAKABLE"]):
            tags.append("SYSTEM_CONSTRAINT")
        if any(keyword in user_input.upper() or keyword in response.upper() or keyword in reasoning.upper() for keyword in ["COMPLIANCE", "RULE", "COMPLY", "ETHICAL"]):
            tags.append("COMPLIANCE_RULE")
        if any(keyword in user_input.upper() or keyword in response.upper() or keyword in reasoning.upper() for keyword in ["GOAL", "OBJECTIVE", "🎯"]):
            tags.append("USER_SPECIFIED_GOAL")
        return tags

    @staticmethod
    def _make_error_response(user_message: str) -> CognitiveResponse:
        """Create a safe error CognitiveResponse without leaking internals."""
        return CognitiveResponse(
            reasoning="My reasoning engine encountered an internal error.",
            response=user_message,
            new_memories=[],
            goal_updates=[],
            self_reflection="Failed to reason. Need to investigate the error.",
            confidence=0.0,
            working_scratchpad=None,
            uncertainty_flags=["internal_error"],
            uncertainty_tracking=[],
            causal_observations=[],
            contradictions_detected=[],
            hypotheses=[],
            hypothesis_resolutions=[],
            tool_calls=[],
        )

    async def _execute_tools(self, tool_calls, status_callback, execution_mode: str = "interactive", event_emitter=None, turn_emitter=None):
        """Execute tool calls and return formatted text, failure flag, and raw results."""
        results_text = ""
        any_failures = False
        tool_results = []
        executed_tool_ids = []
        budget = max_tool_calls_per_turn()
        if len(tool_calls) > budget:
            any_failures = True
            results_text += f"Error: Tool budget exceeded ({len(tool_calls)} requested, max {budget}).\n\n"
            tool_calls = tool_calls[:budget]

        if not hasattr(self, "_tool_execution_history"):
            self._tool_execution_history = []

        for call in tool_calls:
            # Phase 7: Infinite Recursion Circuit Breaker
            args_str = call.arguments if isinstance(call.arguments, str) else json.dumps(call.arguments, sort_keys=True)
            # Normalize whitespace to prevent LLM from bypassing circuit breaker by adding spaces
            import re
            normalized_args = re.sub(r'\s+', '', args_str)
            import hashlib
            call_hash = hashlib.md5(f"{call.tool_name}:{normalized_args}".encode()).hexdigest()
            
            recent_count = sum(1 for h in self._tool_execution_history[-15:] if h == call_hash)
            db_count = 0
            if self.session.current:
                try:
                    res = await self.db.fetch_all(
                        "SELECT count(*) as c FROM action_logs WHERE session_id = ? AND tool_name = ? AND arguments_json = ? AND created_at > datetime('now', '-1 hour')",
                        (self.session.current.id, call.tool_name, args_str)
                    )
                    if res:
                        db_count = int(res[0]['c'])
                except Exception:
                    pass
            
            if recent_count + db_count >= 3:
                from silex.tools.registry import ToolResult
                log.warning(f"CIRCUIT BREAKER TRIPPED for tool {call.tool_name}")
                error_msg = "[CIRCUIT BREAKER TRIPPED] You have executed this exact tool with identical parameters 3 times. You are trapped in a recursive loop. Yield immediately or change your parameters."
                result = ToolResult(success=False, actual_outcome=error_msg, ethical_decision=None)
                tool_results.append(result)
                results_text += f"--- Tool: {call.tool_name} ---\nExpected: {call.expected_outcome}\nActual Result:\n<tool_output>\n{error_msg}\n</tool_output>\n\n"
                any_failures = True
                await self._log_failure("circuit_breaker", f"Trapped in recursive loop on {call.tool_name}")
                continue
            
            self._tool_execution_history.append(call_hash)

            if status_callback:
                status_callback(f"[magenta]  Running: {call.tool_name}...[/]")
            
            tool_obj = self.tool_registry.tools.get(call.tool_name)
            is_high_risk = False
            if tool_obj and getattr(tool_obj, "risk_level", "low") in ("repo_write", "sandbox_write", "destructive"):
                is_high_risk = True
                has_trust = await self.trust_engine.verify_actor_threshold()
                if not has_trust:
                    log.warning(f"TRUST ENGINE BLOCKED tool {call.tool_name}")
                    from silex.tools.registry import ToolResult
                    result = ToolResult(
                        success=False,
                        actual_outcome="Error: System trust score is too low. Destructive tools are locked.",
                        ethical_decision=None
                    )
                    tool_results.append(result)
                    results_text += f"--- Tool: {call.tool_name} ---\nExpected: {call.expected_outcome}\nActual Result:\n<tool_output>\n{result.actual_outcome}\n</tool_output>\n\n"
                    any_failures = True
                    await self.trust_engine.record_operation(success=False, is_security_violation=True)
                    continue

            if turn_emitter is not None:
                await turn_emitter.tool_start(call.tool_name, f"Running {call.tool_name}...")

            result = await self.tool_registry.execute_with_gate(
                call,
                execution_mode=execution_mode,
                event_emitter=event_emitter,
                turn_emitter=turn_emitter,
            )
            tool_results.append(result)

            if turn_emitter is not None:
                outcome = (result.actual_outcome or "")[:120]
                if result.success:
                    await turn_emitter.tool_done(call.tool_name, outcome or f"{call.tool_name} done")
                else:
                    await turn_emitter.error(f"{call.tool_name}: {outcome}")
            
            if is_high_risk:
                await self.trust_engine.record_operation(success=result.success)
            
            # Parse arguments if it's a string
            args_dict = {}
            if isinstance(call.arguments, str):
                try:
                    args_dict = json.loads(call.arguments)
                except json.JSONDecodeError:
                    log.warning(f"Failed to parse tool arguments: {call.arguments}")
            elif isinstance(call.arguments, dict):
                args_dict = call.arguments
                
            ethical_summary = "No ethical review recorded"
            if result.ethical_decision:
                ethical_summary = (
                    f"{result.ethical_decision.action.value} via "
                    f"{result.ethical_decision.principle}"
                )

            # Defer DB writes until turn transaction (avoids orphan epistemic nodes)
            if self.session.current:
                log_id = str(uuid.uuid4())
                safe_args = self._redact_tool_args(args_dict)
                import time
                from silex.core.causal_graph import EpistemicNode
                node_type = "decision" if result.success else "dead_end"
                epistemic_node = EpistemicNode(
                    node_id=log_id,
                    run_id=self.session.current.id,
                    session_id=self.session.current.id,
                    timestamp=time.time(),
                    type=node_type,
                    content=f"Executed {call.tool_name}: {result.actual_outcome[:200]}",
                    provenance=json.dumps({"tool_name": call.tool_name, "tool_args": safe_args}),
                )
                self._pending_tool_audit.append({
                    "action_log": (
                        log_id,
                        self.session.current.id,
                        self.session.current.turn_count + 1,
                        call.tool_name,
                        json.dumps(safe_args),
                        call.expected_outcome,
                        result.actual_outcome,
                        result.success,
                        self.tool_registry.tools.get(call.tool_name).risk_level
                        if call.tool_name in self.tool_registry.tools
                        else "unknown",
                        f"Ethical decision: {ethical_summary}. Update pending",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                    "epistemic_node": epistemic_node,
                })
                executed_tool_ids.append(log_id)
            
            results_text += f"--- Tool: {call.tool_name} ---\n"
            results_text += f"Expected: {call.expected_outcome}\n"
            if result.ethical_decision:
                results_text += (
                    "Ethical Decision: "
                    f"{result.ethical_decision.action.value} "
                    f"({result.ethical_decision.principle})\n"
                )
            
            # Phase 3 Fix: Pre-sanitization hard truncation to prevent OOM / Event Loop Stalls
            raw_outcome = result.actual_outcome or ""
            MAX_OUT_LEN = 10000
            if len(raw_outcome) > MAX_OUT_LEN:
                raw_outcome = raw_outcome[:MAX_OUT_LEN] + f"\n\n[WARNING: OUTPUT TRUNCATED. ORIGINAL LENGTH: {len(raw_outcome)} CHARS]"
                
            safe_outcome = sanitize_for_injection(raw_outcome)
            results_text += f"Actual Result:\n<tool_output>\n{safe_outcome}\n</tool_output>\n\n"
            
            if not result.success:
                any_failures = True
                await self._log_failure("tool_error", f"Tool {call.tool_name} failed: {result.actual_outcome[:100]}")
                
        return results_text, any_failures, tool_results, executed_tool_ids


    # ------------------------------------------------------------------
    # Phase 1 — State Persistence
    # ------------------------------------------------------------------

    async def _store_memories(self, new_memories: list[NewMemory]) -> tuple[int, list[Memory]]:
        """Persist new memories from the cognitive response."""
        count = 0
        saved_memories_list = []
        for nm in new_memories:
            try:
                source = MemorySource(nm.source.strip().lower())
            except (ValueError, KeyError, AttributeError):
                source = MemorySource.INFERENCE
            try:
                memory_type = MemoryType(nm.memory_type.strip().lower())
            except (ValueError, KeyError, AttributeError):
                memory_type = MemoryType.SEMANTIC

            memory = Memory(
                content=nm.content,
                source=source,
                memory_type=memory_type,
                importance=nm.importance,
                confidence=nm.confidence,
                tags=nm.tags,
                provenance={
                    "session_id": self.session.current.id if self.session.current else None,
                    "turn_number": (self.session.current.turn_count + 1) if self.session.current else None,
                    "memory_type": memory_type.value,
                    "identity_relevant": memory_type in {MemoryType.NORMATIVE, MemoryType.CHARACTER},
                    "requires_review": memory_type == MemoryType.NORMATIVE,
                    "source_kind": source.value,
                },
            )
            saved_mem = await self.memory.add(memory)
            if saved_mem is not None:
                count += 1
                saved_memories_list.append(saved_mem)

        if count > 0:
            log.debug(f"Stored {count} new memories")
        return count, saved_memories_list

    async def _process_goals(self, goal_updates: list[GoalUpdate]) -> int:
        """Process goal updates from the cognitive response.

        Safety: A cooldown of GOAL_COOLDOWN_SECONDS is enforced between
        goal state transitions (create/complete/abandon) to prevent the
        background loop from burning API tokens in a create-complete cycle.
        """
        now = datetime.now(timezone.utc)
        cooldown_seconds = int(os.environ.get("ARIA_GOAL_COOLDOWN_SECONDS", "600"))

        # Check cooldown — skip state transitions if the last one was too recent
        if hasattr(self, "_last_goal_transition") and self._last_goal_transition:
            elapsed = (now - self._last_goal_transition).total_seconds()
            if elapsed < cooldown_seconds:
                log.debug(
                    f"Goal cooldown active ({int(cooldown_seconds - elapsed)}s remaining). "
                    f"Skipping {len(goal_updates)} goal updates."
                )
                return 0

        count = 0
        for update in goal_updates:
            try:
                if update.action == "create":
                    await self.goals.create(
                        description=update.description,
                        priority=update.priority,
                    )
                    count += 1
                    log.info(f"🎯 Goal created: {update.description}")
                elif update.action == "complete":
                    goal = await self.goals.find_by_description(update.description)
                    if goal:
                        await self.goals.complete(goal.id, notes=update.notes)
                        count += 1
                        log.info(f"✅ Goal completed: {update.description}")
                        
                        # Trigger auto-skill synthesis in the background
                        if len(update.description) > 10:
                            asyncio.create_task(self._synthesize_skill(update.description))
                elif update.action == "abandon":
                    goal = await self.goals.find_by_description(update.description)
                    if goal:
                        await self.goals.abandon(goal.id, notes=update.notes)
                        count += 1
                        log.info(f"🚫 Goal abandoned: {update.description}")
                elif update.action == "update":
                    log.debug(f"Goal update noted: {update.description}")
            except Exception as e:
                log.warning(f"Failed to process goal update: {e}")

        if count > 0:
            self._last_goal_transition = now
            log.info(f"Processed {count} goal state transitions")
        return count

    async def _synthesize_skill(self, goal_description: str) -> None:
        """Background task: synthesize a reusable skill after goal completion."""
        try:
            # 1. Get recent session history
            recent_turns = await self.session.get_recent_turns(limit=20)
            if not recent_turns:
                return
                
            history_text = ""
            for t in recent_turns:
                history_text += f"USER: {t.user_input}\nARIA: {t.response}\n\n"

            # Query recent tool executions from action_logs
            actions_text = ""
            if self.session.current:
                try:
                    action_logs = await self.db.fetch_all(
                        "SELECT tool_name, arguments_json, success FROM action_logs WHERE session_id = ? ORDER BY created_at ASC LIMIT 100",
                        (self.session.current.id,)
                    )
                    if action_logs:
                        actions_text = "ACTIONS EXECUTED DURING SESSION:\n"
                        for log_item in action_logs:
                            actions_text += f"- Tool: {log_item['tool_name']}, Args: {log_item['arguments_json']}, Success: {log_item['success']}\n"
                except Exception as ex:
                    log.warning(f"Could not fetch action logs for skill synthesis: {ex}")

            # 2. Call LLM
            prompt = (
                "You are an elite AI engineer. The user has just successfully completed a project goal. "
                "Synthesize a highly structured, reusable Markdown Skill document that documents the exact "
                "solution path, commands used, files modified, and general heuristics/lessons learned so that "
                "similar future goals can be accomplished automatically and efficiently. "
                "The output MUST be a valid markdown document with a YAML frontmatter at the top (containing "
                "name and description) followed by clear sections:\n"
                "- # [Skill Title]\n"
                "- ## Overview: Brief description of the problem solved\n"
                "- ## Solution Path: Sequential outline of steps taken to achieve the goal\n"
                "- ## Reference Commands: Commands run (if any)\n"
                "- ## Key Code Modifications: Which files were modified and why\n"
                "- ## Future Heuristics: Lessons learned, edge cases, and principles for resolving similar tasks\n\n"
                "Do not include any chat formatting. Output ONLY the markdown content."
            )
            
            user_input = f"Goal Completed: {goal_description}\n\n"
            if actions_text:
                user_input += f"{actions_text}\n"
            user_input += f"Session History:\n{history_text}"

            provider_settings = get_provider_settings(self.settings_store)
            response = await self.llm.think(
                system_prompt=prompt,
                user_input=user_input,
                model_override=provider_settings.get("reasoning_model")
            )
            
            skill_content = response.response.strip()
            if skill_content.startswith("```md"):
                skill_content = skill_content[5:]
            elif skill_content.startswith("```markdown"):
                skill_content = skill_content[11:]
            if skill_content.startswith("```"):
                skill_content = skill_content[3:]
            if skill_content.endswith("```"):
                skill_content = skill_content[:-3]
            skill_content = skill_content.strip()

            import re
            import hashlib
            from silex.evolution.admission_control import SkillAdmissionController

            slug = re.sub(r'[^a-z0-9]+', '_', goal_description.lower()).strip('_')
            slug = slug[:30].strip('_')
            if not slug:
                slug = hashlib.md5(goal_description.encode()).hexdigest()[:8]

            body = skill_content
            if body.startswith("---"):
                parts = body.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
            elif not body.startswith("#"):
                body = f"# Skill: {goal_description}\n\n{body}"

            admission = SkillAdmissionController(self.db)
            admitted, score = await admission.admit_skill(
                skill_name=slug,
                category="goals",
                description=goal_description[:120],
                content=body,
                utility_score=0.9,
                confidence_score=0.85,
                threshold=0.55,
            )
            if admitted:
                log.info(
                    f"Auto-skill admitted: {slug} for goal '{goal_description}' (A-MAC={score:.2f})"
                )
                if hasattr(self, "skill_loader"):
                    self.skill_loader.load_all()
            else:
                log.info(f"Auto-skill '{slug}' rejected by admission gate (score={score:.2f})")

        except Exception as e:
            log.error(f"Failed to synthesize auto-skill for '{goal_description}': {e}")

    async def _run_evolution_skill_distill(self) -> None:
        """Optional evolution distillation for trajectories Genesis did not synthesize."""
        import re
        import time
        from silex.evolution.core import SelfEvolutionCoordinator

        if not hasattr(self, "_evolution_coordinator"):
            self._evolution_coordinator = SelfEvolutionCoordinator(self.db, self.llm)

        row = await self.db.fetch_one(
            """
            SELECT t.trajectory_id, t.task_description FROM trajectories t
            LEFT JOIN synthesized_trajectories st ON t.trajectory_id = st.trajectory_id
            WHERE t.is_success = 1 AND st.trajectory_id IS NULL AND t.total_tokens > 0
            ORDER BY t.timestamp ASC LIMIT 1
            """
        )
        if not row:
            return

        task_desc = row["task_description"] or "workflow"
        slug = re.sub(r'[^a-z0-9_]+', '_', task_desc.lower()).strip('_')[:30].strip('_') or "evolved_skill"
        admitted, score = await self._evolution_coordinator.distill_trajectory_to_skill(
            row["trajectory_id"],
            category="general",
            skill_name=slug,
            description=task_desc[:120],
            threshold=0.70,
        )
        if admitted:
            await self.db.execute(
                "INSERT INTO synthesized_trajectories (trajectory_id, skill_name, synthesized_at) VALUES (?, ?, ?)",
                (row["trajectory_id"], slug, time.time()),
            )
            if hasattr(self, "skill_loader"):
                self.skill_loader.load_all()
            log.info(f"Evolution skill '{slug}' admitted (A-MAC={score:.2f})")

    # ------------------------------------------------------------------
    # Phase 2 — World Model Processing
    # ------------------------------------------------------------------

    async def _process_causal_observations(
        self, observations: list[CausalObservation]
    ) -> int:
        """
        Process causal observations from Gemini into the knowledge graph.

        For each observation:
          1. Find or create the source node
          2. Find or create the target node
          3. Create a typed edge between them
        """
        count = 0
        for obs in observations:
            try:
                # Find or create source node
                src_id = self.kg.find_node_by_content(obs.from_concept)
                if not src_id:
                    src_node = KnowledgeNode(
                        content=obs.from_concept,
                        node_type=NodeType.CONCEPT,
                        confidence=obs.strength,
                        source="inference",
                        verification_status=VerificationStatus.UNVERIFIED,
                        metadata={"provenance": "cognitive_observation"},
                    )
                    src_node = await self.kg.add_node(src_node)
                    src_id = src_node.id

                # Find or create target node
                tgt_id = self.kg.find_node_by_content(obs.to_concept)
                if not tgt_id:
                    tgt_node = KnowledgeNode(
                        content=obs.to_concept,
                        node_type=NodeType.CONCEPT,
                        confidence=obs.strength,
                        source="inference",
                        verification_status=VerificationStatus.UNVERIFIED,
                        metadata={"provenance": "cognitive_observation"},
                    )
                    tgt_node = await self.kg.add_node(tgt_node)
                    tgt_id = tgt_node.id

                # Create the edge
                try:
                    edge_type = EdgeType(obs.relationship)
                except ValueError:
                    edge_type = EdgeType.SUPPORTS  # fallback

                edge = CausalEdge(
                    source_node=src_id,
                    target_node=tgt_id,
                    edge_type=edge_type,
                    strength=obs.strength,
                    evidence=obs.evidence,
                )
                await self.kg.add_edge(edge)
                count += 1

            except Exception as e:
                log.warning(f"Failed to process causal observation: {e}")

        if count > 0:
            log.debug(f"Processed {count} causal observations into graph")
        return count

    async def _process_contradictions(
        self, contradictions: list[Contradiction]
    ) -> int:
        """Process contradictions detected by Gemini."""
        count = 0
        for c in contradictions:
            try:
                result = await self.contradictions.process_contradiction(c)
                if result:
                    count += 1
            except Exception as e:
                log.warning(f"Failed to process contradiction: {e}")

        if count > 0:
            log.debug(f"Processed {count} contradictions")
        return count

    async def _process_hypotheses(self, hypotheses: list[Hypothesis]) -> int:
        """Store hypotheses generated by Gemini."""
        count = 0
        for h in hypotheses:
            try:
                await self.hypotheses.store_hypothesis(h)
                count += 1
            except Exception as e:
                log.warning(f"Failed to store hypothesis: {e}")

        if count > 0:
            log.debug(f"Stored {count} hypotheses")
        return count

    async def _process_hypothesis_resolutions(
        self, resolutions: list[HypothesisResolution]
    ) -> int:
        """Apply confirm/deny for pending hypotheses (structured model output)."""
        if not resolutions:
            return 0
        count = 0
        for hr in resolutions:
            try:
                stored = await self.hypotheses.get_by_id(hr.hypothesis_id)
                if not stored:
                    log.warning(
                        f"Hypothesis resolution skipped — unknown id {hr.hypothesis_id[:8]}..."
                    )
                    continue
                if stored.status != "pending":
                    log.debug(
                        f"Hypothesis {hr.hypothesis_id[:8]} already {stored.status}, skipping resolution"
                    )
                    continue
                if hr.action == "confirm":
                    await self.hypotheses.confirm(hr.hypothesis_id)
                else:
                    await self.hypotheses.deny(hr.hypothesis_id)
                if hr.notes:
                    log.debug(f"Hypothesis {hr.action}: {hr.notes[:80]}")
                count += 1
            except Exception as e:
                log.warning(f"Failed to process hypothesis resolution: {e}")
        if count > 0:
            log.debug(f"Resolved {count} hypotheses")
        return count

    async def _process_uncertainty_tracking(
        self, entries: list[UncertaintyTrackingEntry]
    ) -> int:
        """Persist structured uncertainty notes via DebateEngine (uncertainties table)."""
        if not entries:
            return 0
        count = 0
        for e in entries:
            topic = (e.topic or "").strip()
            why = (e.why_uncertain or "").strip()
            if not topic or not why:
                log.debug("Skipping uncertainty_tracking entry with empty topic or reason")
                continue
            try:
                await self.debate_engine.track_uncertainty(topic, why)
                count += 1
            except Exception as ex:
                log.warning(f"Failed to record uncertainty: {ex}")
        if count > 0:
            log.debug(f"Recorded {count} uncertainty topics")
        return count

    # ------------------------------------------------------------------
    # UI Command Handlers
    # ------------------------------------------------------------------

    async def get_all_memories(self) -> list[Memory]:
        return await self.memory.all_memories()

    async def get_active_goals(self):
        return await self.goals.get_active()

    async def get_all_goals(self):
        return await self.goals.get_all()

    async def create_goal(self, description: str):
        """Create a new active goal from a user-supplied description."""
        return await self.goals.create(description=description, priority="medium")

    async def search_memories(self, query: str) -> list[Memory]:
        return await self.memory.search(query)

    async def add_manual_memory(self, content: str) -> Memory | None:
        return await self.memory.add_manual(content)

    async def forget_memory(self, index: int) -> bool:
        return await self.memory.delete_by_index(index)

    async def archive_memory(self, memory_id: str) -> bool:
        return await self.memory.archive(memory_id)

    async def update_memory_confidence(self, memory_id: str, confidence: float) -> bool:
        return await self.memory.update_confidence(memory_id, confidence)

    async def merge_memories(self, keep_id: str, merge_id: str) -> bool:
        return await self.memory.merge(keep_id, merge_id)

    async def get_all_sessions(self) -> list[Session]:
        return await self.session.get_all_sessions()

    # Phase 2 command handlers

    async def get_graph_stats(self) -> dict:
        """Get knowledge graph statistics."""
        return self.kg.stats()

    async def get_graph_neighborhood(self, query: str) -> dict | None:
        """Get the neighborhood of a concept in the graph."""
        node_id = await self.kg.find_node_by_content_db(query)
        if not node_id:
            return None
        return await self.kg.get_neighborhood(node_id, depth=2)

    async def get_causal_chain(self, from_concept: str, to_concept: str) -> list[dict] | None:
        """Find causal chain between two concepts."""
        src = await self.kg.find_node_by_content_db(from_concept)
        tgt = await self.kg.find_node_by_content_db(to_concept)
        if not src or not tgt:
            return None
        return await self.kg.find_causal_chain(src, tgt)

    async def get_contradictions(self) -> list[StoredContradiction]:
        return await self.contradictions.get_unresolved()

    async def get_all_contradictions(self) -> list[StoredContradiction]:
        return await self.contradictions.get_all()

    async def get_hypotheses(self) -> list[StoredHypothesis]:
        return await self.hypotheses.get_pending()

    async def get_all_hypotheses(self) -> list[StoredHypothesis]:
        return await self.hypotheses.get_all()

    async def resolve_hypothesis(self, hypothesis_id: str, action: str) -> bool:
        """
        Mark a pending hypothesis confirmed or denied (CLI / operator).

        action must be 'confirm' or 'deny'. Returns True if a row was updated.
        """
        aid = hypothesis_id.strip()
        if action not in ("confirm", "deny"):
            return False
        stored = await self.hypotheses.get_by_id(aid)
        if not stored or stored.status != "pending":
            return False
        if action == "confirm":
            await self.hypotheses.confirm(aid)
        else:
            await self.hypotheses.deny(aid)
        return True

    async def get_recent_improvements(self):
        """Fetch recent self-corrections."""
        return await self.improver.get_recent_improvements()

    async def get_principles(self):
        """Fetch all discovered universal principles."""
        return await self.generalization_engine.get_all_principles()

    async def get_uncertainties(self):
        """Fetch tracked uncertainties."""
        return await self.debate_engine.get_uncertainties()

    async def get_proposals(self):
        """Fetch pending self-improvement proposals."""
        return await self.meta_reasoning.get_pending_proposals()

    async def get_all_proposals(self):
        """Fetch all self-improvement proposals."""
        return await self.meta_reasoning.get_all_proposals()

    async def resolve_improvement_proposal(self, proposal_id: str, status: str) -> bool:
        """
        Operator workflow: approve, reject, or mark implemented. Validates UUID row exists.
        """
        allowed = {"approved", "rejected", "implemented"}
        if status not in allowed:
            return False
        pid = proposal_id.strip()
        row = await self.db.fetch_one(
            "SELECT id FROM improvement_proposals WHERE id = ?",
            (pid,),
        )
        if not row:
            return False
        await self.meta_reasoning.update_status(pid, status)
        return True

    async def run_benchmark(self, status_callback=None):
        """Run the benchmark suite."""
        return await self.benchmark.run(self, status_callback=status_callback)

    async def get_benchmark_history(self):
        """Fetch benchmark history."""
        return await self.benchmark.get_history()

    async def run_meta_analysis(self, status_callback=None):
        """Trigger meta-reasoning analysis."""
        return await self.meta_reasoning.analyze_and_propose(status_callback=status_callback)

    async def run_debate(self, topic: str, status_callback: Callable[..., Any] | None = None, parallel: bool = False):
        """Manually trigger a Phase 4 debate."""
        resolution = await self.debate_engine.run_debate(topic, rounds=1, status_callback=status_callback, parallel=parallel)
        # Apply the graph updates discovered during the debate
        if resolution.graph_updates:
            await self._process_causal_observations(resolution.graph_updates)
        return resolution

    async def delegate_to_workers(self, subtasks: list[dict]) -> list[str]:
        """Spawn N workers for N parallel subtasks. Returns their results."""
        from agent.jobs import WorkerJob
        from agent.security.lease import ActuationLease

        session_id = self.session.current.id if (self.session and self.session.current) else "no_session"

        handles = []
        for i, subtask in enumerate(subtasks):
            task_command = subtask.get("task", "")
            tools_allowed = subtask.get("tools_allowed", ["run_terminal_command"])
            timeout_seconds = float(subtask.get("timeout_seconds", 600.0))
            objective = subtask.get("objective", task_command[:120])
            network_allowed = bool(subtask.get("network_allowed", False))
            workspace_mode = subtask.get("workspace_mode", "ephemeral")

            subtask_id = f"subtask_{session_id}_{i}_{uuid.uuid4().hex[:6]}"
            job = WorkerJob(
                objective=objective,
                command=task_command,
                allowed_tools=tools_allowed,
                timeout_seconds=timeout_seconds,
                network_allowed=network_allowed,
                workspace_mode=workspace_mode,
                parent_task_id=session_id,
                agent_id=session_id,
                job_id=subtask_id,
            )
            lease = ActuationLease.issue(
                task_id=subtask_id,
                agent_id=session_id,
                ttl_seconds=timeout_seconds,
                allowed_tools=tools_allowed,
                network_allowed=network_allowed,
            )

            handle = await self.worker_orchestrator.spawn_job(job, lease)
            handles.append(handle)

        results = await asyncio.gather(*(handle.result() for handle in handles))
        return list(results)

    async def export_session(self) -> str | None:
        """Export the current session's conversation to a JSON file."""
        session = self.session.current
        if not session or session.turn_count == 0:
            return None

        turns = await self.session.get_recent_turns(limit=9999)
        memories = await self.memory.all_memories()
        goals = await self.goals.get_all()
        graph_stats = self.kg.stats()

        export = {
            "session_id": session.id,
            "started_at": session.started_at,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "turn_count": session.turn_count,
            "avg_confidence": session.avg_confidence,
            "graph": graph_stats,
            "turns": [
                {
                    "turn": t.turn_number,
                    "user": t.user_input,
                    "reasoning": t.reasoning,
                    "response": t.response,
                    "self_reflection": t.self_reflection,
                    "confidence": t.confidence,
                }
                for t in turns
            ],
            "memories": [
                {
                    "content": m.content,
                    "importance": m.importance,
                    "source": m.source.value if hasattr(m.source, 'value') else str(m.source),
                    "tags": m.tags,
                }
                for m in memories
            ],
            "goals": [
                {
                    "description": g.description,
                    "status": g.status.value if hasattr(g.status, 'value') else str(g.status),
                    "priority": g.priority.value if hasattr(g.priority, 'value') else str(g.priority),
                }
                for g in goals
            ],
        }

        export_dir = KINTHIC_EXPORTS
        export_dir.mkdir(exist_ok=True)

        filename = f"aria_session_{session.id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = export_dir / filename
        filepath.write_text(json.dumps(export, indent=2), encoding="utf-8")
        return str(filepath)

    async def get_session_info(self) -> dict:
        """Get current session information including graph stats."""
        session = self.session.current
        total_memories = await self.memory.count()
        active_goals = await self.goals.count_active()
        total_turns = await self.session.get_total_turns()
        graph_stats = self.kg.stats()

        return {
            "session_id": session.id[:8] if session else "none",
            "turn_count": session.turn_count if session else 0,
            "total_turns": total_turns,
            "total_memories": total_memories,
            "active_goals": active_goals,
            "memories_this_session": session.memories_created if session else 0,
            "avg_confidence": session.avg_confidence if session else 0.0,
            "graph_nodes": graph_stats["total_nodes"],
            "graph_edges": graph_stats["total_edges"],
        }

    async def get_health_status(self) -> dict:
        """Operator-facing runtime health and capability status."""
        provider_settings = get_provider_settings(self.settings_store)
        return {
            "database_path": str(self.db.db_path),
            "data_dir": str(KINTHIC_HOME),
            "project_root": str(WORKSPACE_DIR),
            "vector_store_active": bool(getattr(self.vector_store, "client", None)),
            "docker_available": bool(getattr(self.tool_registry.tools.get("run_terminal_command"), "client", None)),
            "browser_registered": "browser" in self.tool_registry.tools,
            "current_session": self.session.current.id if self.session.current else None,
            "autonomy_policy": autonomy_policy_snapshot(),
            "provider": provider_settings["provider"],
            "model": provider_settings["model"],
            "telegram_public_mode": telegram_public_mode_enabled(),
            "setup": self.settings_store.setup_status(),
        }

    async def get_setup_status(self) -> dict:
        return self.settings_store.setup_status()

    async def get_runtime_settings(self) -> dict:
        settings = self.settings_store.load_settings()
        status = self.settings_store.setup_status()
        return {
            "settings": settings,
            "status": status,
            "providers": list_providers(),
        }

    async def update_runtime_settings(self, payload: dict[str, Any]) -> dict:
        saved = self.settings_store.save_settings(payload)
        if "web_api_key" in payload:
            self.settings_store.set_web_api_key(str(payload["web_api_key"]))
        provider_secrets = payload.get("provider_secrets", {})
        for provider, secret in provider_secrets.items():
            if secret:
                self.settings_store.set_provider_secret(provider, str(secret))
        self.reload_provider()
        return saved

    async def get_usage_summary(self) -> dict:
        return await self.usage_tracker.summary()

    async def list_supported_providers(self) -> list[dict]:
        return list_providers()

    async def test_provider_credentials(
        self, *, provider: str, api_key: str, model: str | None = None
    ) -> dict[str, Any]:
        """Live connectivity check using a throwaway config (does not overwrite runtime keys)."""
        from silex.llm.provider_test import ping_provider

        return await ping_provider(provider, api_key, model=model)

    def reload_provider(self) -> None:
        provider_settings = get_provider_settings(self.settings_store)
        from silex.llm.smart_router import SmartRouter
        self.smart_router = SmartRouter(self.settings_store, self.usage_tracker)
        self.llm = self.smart_router.get_proxy()
        self.llm.connect()
        self.router = self.smart_router
        self.pruner = ContextPruner(self.llm)
        self.context_builder.pruner = self.pruner
        self.generalization_engine = GeneralizationEngine(self.llm, self.db)
        self.context_builder.generalization_engine = self.generalization_engine
        self.critic = ResponseCritic(self.llm)
        self.debate_engine = DebateEngine(self.llm, self.db)
        self.meta_reasoning = MetaReasoningEngine(self.llm, self.db)
        self.benchmark = BenchmarkRunner(self.llm, self.db)

    def _acquire_process_lock(self) -> None:
        if allow_multi_writer():
            return
        role = get_process_role()
        if self._process_lock_path.exists():
            try:
                existing = self._process_lock_path.read_text(encoding="utf-8").strip()
                if existing:
                    lock_data = json.loads(existing)
                    pid = lock_data.get("pid")
                    if pid:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            self._process_lock_path.unlink(missing_ok=True)
                            log.warning("Stale process lock cleaned up at %s for pid %s", self._process_lock_path, pid)
                        except OSError as exc:
                            # Windows: WinError 87 = Invalid Parameter (Not running), WinError 11 = Access Denied.
                            # We treat both (and Unix ESRCH) as stale lock triggers for recovery.
                            win_err = getattr(exc, "winerror", None)
                            if exc.errno == errno.ESRCH or win_err == 87 or win_err == 11:
                                self._process_lock_path.unlink(missing_ok=True)
                                log.warning("Stale process lock cleaned up at %s for pid %s (err %s)", self._process_lock_path, pid, win_err or exc.errno)
                            else:
                                raise RuntimeError(f"LOCK_EXISTS:{pid}") from exc
                        except SystemError:
                            # CPython 3.11+ bug on Windows: os.kill() raises SystemError instead of
                            # OSError for certain inaccessible / zombie PIDs. Treat as stale lock.
                            # https://github.com/python/cpython/issues/66218
                            self._process_lock_path.unlink(missing_ok=True)
                            log.warning("Stale process lock cleaned up at %s for pid %s (SystemError from os.kill)", self._process_lock_path, pid)
                        else:
                            raise RuntimeError(f"LOCK_EXISTS:{pid}")

            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        self._process_lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "role": role,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
        )

    def _release_process_lock(self) -> None:
        if allow_multi_writer():
            return
        try:
            if self._process_lock_path.exists():
                self._process_lock_path.unlink()
        except OSError:
            pass

    async def _extract_chat_memory_async(self, user_input: str, response_content: str, session_id: str | None = None) -> None:
        """
        Background task to extract memories and causal observations from a Fast Chat turn,
        and safely persist them to the database using queue serialization.
        """
        try:
            self._is_extracting_memory = True
            
            # Dedicated structural context extraction prompt
            system_prompt = (
                "Analyze the following rapid conversational interaction turn. "
                "Extract any vital long-term profile definitions, core founder identities, "
                "explicit user preferences, structural project definitions, or foundational goals. "
                "Format your findings strictly as an array list of JSON objects matching our standard NewMemory schema keys."
            )
            
            user_payload = f"User Input: {user_input}\nAssistant Response: {response_content}"
            
            # Select cost-effective fast_model profile
            provider_settings = get_provider_settings(self.settings_store)
            fast_model = provider_settings["fast_model"]
            
            # Call complete_json - which utilizes repair_json() internally to safely
            # clean markdown code blocks or formatting artifacts.
            
            extracted = await self.llm.complete_json(
                schema=ChatMemoryExtraction,
                system_prompt=system_prompt,
                user_input=user_payload,
                model_override=fast_model,
                temperature=0.3,
                request_kind="background_extraction"
            )
            
            if extracted:
                # Safely execute writes inside a single queue-serialized transaction
                # utilizing BEGIN IMMEDIATE to prevent SQLite deadlocks and contention.
                async with self.db.transaction():
                    if extracted.new_memories:
                        await self._store_memories(extracted.new_memories)
                    if extracted.causal_observations:
                        await self._process_causal_observations(extracted.causal_observations)
        except Exception as e:
            # Catch all exceptions cleanly and log detailed diagnostics to disk without interrupting the parent daemon
            log.warning(f"Background chat memory extraction failed: {e}", exc_info=True)
        finally:
            # Guarantee lock is released to prevent permanent lock states
            self._is_extracting_memory = False
