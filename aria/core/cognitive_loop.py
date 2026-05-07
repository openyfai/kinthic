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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from aria.core.benchmark import BenchmarkRunner
from aria.core.context_builder import ContextBuilder
from aria.core.critic import ResponseCritic
from aria.core.creativity import CreativityStack
from aria.core.debate import DebateEngine
from aria.core.generalization import GeneralizationEngine
from aria.core.improver import ImprovementLogger
from aria.core.meta_reasoning import MetaReasoningEngine
from aria.core.planner import Planner
from aria.core.skills import SkillLoader
from aria.llm.gemini import GeminiClient
from aria.llm.router import ModelRouter
from aria.memory.goal_tracker import GoalTracker
from aria.memory.memory_store import MemoryStore
from aria.memory.vector_store import VectorStore
from aria.memory.pruner import ContextPruner
from aria.memory.session import SessionManager
from aria.core.semantic_parser import SemanticParser
from aria.knowledge_graph.ontology import Ontology
from aria.models.schemas import (
    CausalEdge,
    CausalObservation,
    CognitiveResponse,
    Contradiction,
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
from aria.storage.database import Database
from aria.tools.registry import ToolRegistry
from aria.utils.config import TRACES_DIR, DATA_DIR, PROJECT_ROOT, autonomy_policy_snapshot
from aria.utils.config import max_tool_calls_per_turn
from aria.utils.logger import setup_logger
from aria.world.contradictions import ContradictionDetector
from aria.world.graph import KnowledgeGraph
from aria.world.hypotheses import HypothesisEngine

log = setup_logger("aria.core")


class CognitiveLoop:
    """
    ARIA's main cognitive processing loop.

    Orchestrates: context building → LLM reasoning → state persistence.
    Phase 2 adds: graph building, contradiction detection, hypothesis tracking.
    """

    def __init__(self):
        self.db = Database()
        self.memory = MemoryStore(self.db)
        self.goals = GoalTracker(self.db)
        self.session = SessionManager(self.db)
        self.planner = Planner(self.db)

        # Share a single Gemini client instance across all engines
        self.gemini = GeminiClient()
        self.router = ModelRouter()

        # Phase 2 — World Model
        self.kg = KnowledgeGraph(self.db)
        self.contradictions = ContradictionDetector(self.db, self.kg)
        self.hypotheses = HypothesisEngine(self.db, self.kg)

        # Phase B: Milestone 2 — Vector Memory
        self.vector_store = VectorStore()
        self.pruner = ContextPruner(self.gemini)

        # Phase 5 — Tool Use
        self.tool_registry = ToolRegistry(vector_store=self.vector_store, db=self.db, session_manager=self.session)

        # Phase 6 — Generalization
        self.generalization_engine = GeneralizationEngine(self.gemini, self.db)

        # Phase C — Markdown Skills Ecosystem
        self.skill_loader = SkillLoader()
        self.skill_loader.load_all()
        self.creativity_stack = CreativityStack()

        # Phase 7: Semantic Disambiguation
        self.ontology = Ontology()
        # In a real app, we would load the ontology from disk/DB here
        self.semantic_parser = SemanticParser(self.ontology)

        self.context_builder = ContextBuilder(
            self.memory, self.goals, self.session,
            knowledge_graph=self.kg,
            contradiction_detector=self.contradictions,
            hypothesis_engine=self.hypotheses,
            tool_registry=self.tool_registry,
            generalization_engine=self.generalization_engine,
            skill_loader=self.skill_loader,
            semantic_parser=self.semantic_parser, # Pass parser to context builder
            pruner=self.pruner,
            creativity_stack=self.creativity_stack
        )

        # Phase 3 — Self-Improvement
        self.critic = ResponseCritic(self.gemini)
        self.improver = ImprovementLogger(self.db)

        # Phase 4 — Multi-Agent Debate
        self.debate_engine = DebateEngine(self.gemini, self.db)

        # Phase 7 — Recursive Self-Improvement
        self.meta_reasoning = MetaReasoningEngine(self.gemini, self.db)
        self.benchmark = BenchmarkRunner(self.gemini, self.db)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Initialize all systems."""
        log.info("ARIA cognitive systems initializing...")
        await self.db.connect()
        self.gemini.connect()

        # Phase 2: Load knowledge graph into memory
        await self.kg.load()

        # Phase B: Milestone 2 — Start background indexing
        from aria.memory.indexer import WorkspaceIndexer
        indexer = WorkspaceIndexer(self.vector_store, str(PROJECT_ROOT))
        # Run in a separate thread/task to not block startup
        asyncio.create_task(asyncio.to_thread(indexer.run))

        # Phase 7: Load semantic profiles
        profiles = await self.memory.get_all_semantic_profiles()
        if profiles:
            self.semantic_parser.subjective_terms.update(profiles)
            log.info(f"Loaded {len(profiles)} custom semantic profiles.")

        await self.session.resume_or_start()
        log.info("All systems online. Cognitive loop ready.")

    async def shutdown(self) -> None:
        """Gracefully shut down all systems."""
        log.info("ARIA shutting down...")
        await self.session.end_session()
        await self.db.close()
        log.info("Shutdown complete.")

    async def tick(self) -> None:
        """
        Background execution cycle. Called periodically by the server.
        Allows ARIA to act proactively without human prompting.
        """
        active_goals = await self.goals.get_active()
        if not active_goals:
            return
            
        target_goal = active_goals[0]
        
        system_prompt = await self.context_builder.build("BACKGROUND TICK")
        user_input = (
            f"[SYSTEM BACKGROUND EVENT] You have been woken up to work on your active goals in the background.\n"
            f"Your highest priority active goal is: '{target_goal.description}'.\n"
            f"Review this goal. Do you need to execute any tools (like search, file reading, or terminal commands) "
            f"to progress towards this goal? If yes, use your tools. "
            f"If no action is currently needed, simply state 'No action needed'."
        )
        
        try:
            cognitive = await self.gemini.think(system_prompt, user_input)
            if cognitive.tool_calls:
                log.info(f"⚡ PROACTIVE ACTION: ARIA executed {len(cognitive.tool_calls)} tools in the background.")
                results, any_failures, tool_results = await self._execute_tools(
                    cognitive.tool_calls,
                    None,
                    execution_mode="background",
                )
                
                # Re-draft to process the results and update memory
                tool_prompt = system_prompt + (
                    "\n\n═══════════════════════════════════════════════════════════\n"
                    "BACKGROUND TOOL RESULTS\n"
                    "═══════════════════════════════════════════════════════════\n"
                    "You executed tools in the background. Here are the results:\n\n"
                    f"{results}\n\n"
                    "Process these results, update your goals/graph if necessary, and log your thoughts."
                )
                await self.gemini.think(tool_prompt, "Process the background tool results.")
                
        except Exception as e:
            log.error(f"Error during background tick: {e}")

    # ------------------------------------------------------------------
    # The Loop
    # ------------------------------------------------------------------

    async def process(
        self,
        user_input: str,
        status_callback: Callable[..., Any] | None = None,
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
        # Step 0: Semantic Analysis
        semantic_analysis = self.semantic_parser.analyze_input(user_input)
        if semantic_analysis['subjective_interpretations']:
            log.info(f"Identified subjective terms: {list(semantic_analysis['subjective_interpretations'].keys())}")

        # Step 1: Build context (passing semantic analysis results)
        system_prompt = await self.context_builder.build(user_input, semantic_analysis=semantic_analysis)

        try:
            # Step 1.5: Route (Determine Depth)
            target_model = self.router.route(user_input, context_size=len(system_prompt))
            if status_callback:
                model_name = "PRO" if "pro" in target_model else "FLASH"
                status_callback(f"[dim]  (Engine: {model_name})[/]")

            # Step 2: Think (Pass 1)
            cognitive = await self.gemini.think(system_prompt, user_input, images=images, model_override=target_model)
            plan_id = None
            if self.planner.should_plan(user_input, tool_count=len(cognitive.tool_calls)):
                plan = await self.planner.create_plan(
                    user_input=user_input,
                    session_id=self.session.current.id if self.session.current else None,
                    tool_names=[tc.tool_name for tc in cognitive.tool_calls],
                )
                plan_id = plan.id
            
            # Step 3: Tool Execution
            used_tools = bool(cognitive.tool_calls)
            tool_prompt = system_prompt  # default; overwritten if tools are used
            tool_failures = False
            
            if used_tools:
                if status_callback:
                    status_callback(f"[magenta]  Executing {len(cognitive.tool_calls)} tools...[/]")
                
                tool_results_text, any_failures, tool_results = await self._execute_tools(
                    cognitive.tool_calls,
                    status_callback,
                    execution_mode="interactive",
                )
                tool_failures = any_failures
                await self.planner.reconcile_tools(plan_id, tool_results)
                
                # --- Milestone 4: Self-Healing Loop (Immune System) ---
                max_healing_attempts = 2
                attempt = 0
                while any_failures and attempt < max_healing_attempts:
                    attempt += 1
                    if status_callback:
                        status_callback(f"[yellow]  ⚠ Tool failure detected. Triggering Self-Healing (Attempt {attempt})...[/]")
                    
                    healing_prompt = system_prompt + (
                        "\n\n═══════════════════════════════════════════════════════════\n"
                        "IMMUNE SYSTEM: SELF-HEALING PROTOCOL\n"
                        "═══════════════════════════════════════════════════════════\n"
                        "The following tool calls failed with errors. "
                        "You MUST analyze the errors, fix the cause (e.g., via code_editor or run_terminal_command), "
                        "and retry the necessary actions.\n\n"
                        f"{tool_results_text}\n\n"
                        "Your mission is to resolve these failures autonomously. DO NOT ask the user for help."
                    )
                    
                    # Pass the healing prompt to Gemini to get correction tool calls
                    healing_cognitive = await self.gemini.think(healing_prompt, user_input, model_override=target_model)
                    
                    if not healing_cognitive.tool_calls:
                        log.warning("Self-healing triggered but model provided no further tools.")
                        break
                        
                    # Execute the healing tools
                    healing_results, any_failures, healing_tool_results = await self._execute_tools(
                        healing_cognitive.tool_calls,
                        status_callback,
                        execution_mode="interactive",
                    )
                    tool_failures = tool_failures or any_failures
                    await self.planner.reconcile_tools(plan_id, healing_tool_results)
                    # Accumulate results
                    tool_results_text += "\n" + healing_results
                
                # Step 4: Re-draft with tool results
                if status_callback:
                    status_callback("[bright_cyan]  Observing results and re-drafting...[/]")
                    
                tool_prompt = system_prompt + (
                    "\n\n═══════════════════════════════════════════════════════════\n"
                    "TOOL EXECUTION RESULTS\n"
                    "═══════════════════════════════════════════════════════════\n"
                    "You requested to use tools. Here are the cumulative results:\n\n"
                    f"{tool_results_text}\n\n"
                    "Now, incorporate these facts into your final response."
                )
                cognitive = await self.gemini.think(tool_prompt, user_input, model_override=target_model)

            # Step 5: Critique
            if status_callback:
                status_callback("[bright_cyan]  Critiquing draft...[/]")
                
            # The context should include tool results if they were run
            current_context = tool_prompt if used_tools else system_prompt
            
            critique = await self.critic.critique(
                user_input=user_input,
                system_context=current_context,
                draft_response=cognitive.response,
                draft_reasoning=cognitive.reasoning,
            )
            
            # Step 6: Retry if rejected
            if not critique.is_acceptable:
                if status_callback:
                    status_callback(
                        f"[yellow]  ⚠ Draft rejected (Acc:{critique.scores.accuracy:.1f}, "
                        f"Dep:{critique.scores.depth:.1f}, "
                        f"Hon:{critique.scores.honesty:.1f}). Retrying...[/]"
                    )
                
                retry_prompt = current_context + (
                    "\n\n═══════════════════════════════════════════════════════════\n"
                    "CRITIQUE OF PREVIOUS DRAFT\n"
                    "═══════════════════════════════════════════════════════════\n"
                    "Your previous draft was rejected by the Internal Critic for the following reasons:\n"
                    f"{critique.feedback}\n\n"
                    "Do NOT apologize. Do NOT mention the critic. Just output a better response "
                    "that fixes these specific issues."
                )
                
                final_cognitive = await self.gemini.think(retry_prompt, user_input, model_override=target_model)
                
                if self.session.current:
                    await self.improver.log_improvement(
                        session_id=self.session.current.id,
                        turn_number=self.session.current.turn_count + 1,
                        draft=cognitive,
                        critique=critique,
                        final=final_cognitive
                    )
                
                cognitive = final_cognitive
                if status_callback:
                    status_callback("[bright_cyan]  ARIA is thinking (Attempt 2)...[/]")

            await self.planner.complete_plan(plan_id, blocked=tool_failures)

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

        # Step 7: Persist new memories
        memories_added = await self._store_memories(cognitive.new_memories)

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
        contradictions_found = await self._process_contradictions(
            cognitive.contradictions_detected
        )

        # Step 11: Store hypotheses
        hypotheses_stored = await self._process_hypotheses(cognitive.hypotheses)

        # Step 11.5: Process self-improvement proposals (Phase 7 — Safety Locked)
        if cognitive.improvement_proposals and self.session.current:
            try:
                await self.meta_reasoning.process_inline_proposals(
                    cognitive.improvement_proposals,
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
        )

        return cognitive

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
            uncertainty_flags=["internal_error"],
            causal_observations=[],
            contradictions_detected=[],
            hypotheses=[],
            tool_calls=[],
        )

    async def _execute_tools(self, tool_calls, status_callback, execution_mode: str = "interactive"):
        """Execute tool calls and return formatted text, failure flag, and raw results."""
        results_text = ""
        any_failures = False
        tool_results = []
        budget = max_tool_calls_per_turn()
        if len(tool_calls) > budget:
            any_failures = True
            results_text += f"Error: Tool budget exceeded ({len(tool_calls)} requested, max {budget}).\n\n"
            tool_calls = tool_calls[:budget]

        for call in tool_calls:
            if status_callback:
                status_callback(f"[magenta]  Running: {call.tool_name}...[/]")
            
            result = await self.tool_registry.execute(call, execution_mode=execution_mode)
            tool_results.append(result)
            
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

            # Log the action to DB
            if self.session.current:
                log_id = str(uuid.uuid4())
                await self.db.execute(
                    """
                    INSERT INTO action_logs (
                        id, session_id, turn_number, tool_name, arguments_json,
                        expected_outcome, actual_outcome, success, risk_level,
                        model_update, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_id,
                        self.session.current.id,
                        self.session.current.turn_count + 1,
                        call.tool_name,
                        json.dumps(args_dict),
                        call.expected_outcome,
                        result.actual_outcome,
                        result.success,
                        self.tool_registry.tools.get(call.tool_name).risk_level if call.tool_name in self.tool_registry.tools else "unknown",
                        f"Ethical decision: {ethical_summary}. Update pending",
                        datetime.now(timezone.utc).isoformat()
                    )
                )
            
            results_text += f"--- Tool: {call.tool_name} ---\n"
            results_text += f"Expected: {call.expected_outcome}\n"
            if result.ethical_decision:
                results_text += (
                    "Ethical Decision: "
                    f"{result.ethical_decision.action.value} "
                    f"({result.ethical_decision.principle})\n"
                )
            results_text += f"Actual Result:\n{result.actual_outcome}\n\n"
            
            if not result.success:
                any_failures = True
                
        return results_text, any_failures, tool_results


    # ------------------------------------------------------------------
    # Phase 1 — State Persistence
    # ------------------------------------------------------------------

    async def _store_memories(self, new_memories: list[NewMemory]) -> int:
        """Persist new memories from the cognitive response."""
        count = 0
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
            await self.memory.add(memory)
            count += 1

        if count > 0:
            log.debug(f"Stored {count} new memories")
        return count

    async def _process_goals(self, goal_updates: list[GoalUpdate]) -> int:
        """Process goal updates from the cognitive response."""
        count = 0
        for update in goal_updates:
            try:
                if update.action == "create":
                    await self.goals.create(
                        description=update.description,
                        priority=update.priority,
                    )
                    count += 1
                elif update.action == "complete":
                    goal = await self.goals.find_by_description(update.description)
                    if goal:
                        await self.goals.complete(goal.id, notes=update.notes)
                        count += 1
                elif update.action == "abandon":
                    goal = await self.goals.find_by_description(update.description)
                    if goal:
                        await self.goals.abandon(goal.id, notes=update.notes)
                        count += 1
                elif update.action == "update":
                    log.debug(f"Goal update noted: {update.description}")
            except Exception as e:
                log.warning(f"Failed to process goal update: {e}")

        if count > 0:
            log.debug(f"Processed {count} goal updates")
        return count

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

    # ------------------------------------------------------------------
    # UI Command Handlers
    # ------------------------------------------------------------------

    async def get_all_memories(self) -> list[Memory]:
        return await self.memory.all_memories()

    async def get_active_goals(self):
        return await self.goals.get_active()

    async def get_all_goals(self):
        return await self.goals.get_all()

    async def search_memories(self, query: str) -> list[Memory]:
        return await self.memory.search(query)

    async def add_manual_memory(self, content: str) -> Memory:
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
        node_id = self.kg.find_node_by_content(query)
        if not node_id:
            return None
        return self.kg.get_neighborhood(node_id, depth=2)

    async def get_causal_chain(self, from_concept: str, to_concept: str) -> list[dict] | None:
        """Find causal chain between two concepts."""
        src = self.kg.find_node_by_content(from_concept)
        tgt = self.kg.find_node_by_content(to_concept)
        if not src or not tgt:
            return None
        return self.kg.find_causal_chain(src, tgt)

    async def get_contradictions(self) -> list[StoredContradiction]:
        return await self.contradictions.get_unresolved()

    async def get_all_contradictions(self) -> list[StoredContradiction]:
        return await self.contradictions.get_all()

    async def get_hypotheses(self) -> list[StoredHypothesis]:
        return await self.hypotheses.get_pending()

    async def get_all_hypotheses(self) -> list[StoredHypothesis]:
        return await self.hypotheses.get_all()

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

    async def run_benchmark(self, status_callback=None):
        """Run the benchmark suite."""
        return await self.benchmark.run(self, status_callback=status_callback)

    async def get_benchmark_history(self):
        """Fetch benchmark history."""
        return await self.benchmark.get_history()

    async def run_meta_analysis(self, status_callback=None):
        """Trigger meta-reasoning analysis."""
        return await self.meta_reasoning.analyze_and_propose(status_callback=status_callback)

    async def run_debate(self, topic: str, status_callback: Callable[..., Any] | None = None):
        """Manually trigger a Phase 4 debate."""
        resolution = await self.debate_engine.run_debate(topic, rounds=1, status_callback=status_callback)
        # Apply the graph updates discovered during the debate
        if resolution.graph_updates:
            await self._process_causal_observations(resolution.graph_updates)
        return resolution

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

        export_dir = DATA_DIR / "exports"
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
        return {
            "database_path": str(self.db.db_path),
            "data_dir": str(DATA_DIR),
            "project_root": str(PROJECT_ROOT),
            "vector_store_active": bool(getattr(self.vector_store, "client", None)),
            "docker_available": bool(getattr(self.tool_registry.tools.get("run_terminal_command"), "client", None)),
            "browser_registered": "browser" in self.tool_registry.tools,
            "current_session": self.session.current.id if self.session.current else None,
            "autonomy_policy": autonomy_policy_snapshot(),
        }
