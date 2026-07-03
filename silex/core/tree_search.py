"""
Language Agent Tree Search (LATS) — MCTS-based planning for ARIA/Kronos.
"""

from __future__ import annotations

import asyncio
import math
import uuid
import time
from typing import Any, List, Optional

from silex.models.schemas import CognitiveResponse, ToolCall
from silex.core.causal_graph import EpistemicNode, CausalEdge
from silex.utils.logger import setup_logger
from silex.utils.telemetry import tracer

log = setup_logger("silex.core.tree_search")


class LATSNode:
    """A node in the Language Agent Tree Search representing state & action."""

    def __init__(
        self,
        node_id: str,
        parent: Optional[LATSNode] = None,
        reasoning: str = "",
        response: str = "",
        tool_calls: Optional[List[ToolCall]] = None,
        observation: str = "",
        critic_score: float = 0.0,
        is_acceptable: bool = False,
        feedback: str = "",
        depth: int = 0,
    ) -> None:
        self.node_id = node_id
        self.parent = parent
        self.children: List[LATSNode] = []
        self.reasoning = reasoning
        self.response = response
        self.tool_calls = tool_calls or []
        self.observation = observation
        self.critic_score = critic_score
        self.is_acceptable = is_acceptable
        self.feedback = feedback
        self.depth = depth
        self.commit_hash: Optional[str] = None

        self.visit_count = 0
        self.value_sum = 0.0

    @property
    def value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def ucb1(self, exploration_constant: float = 1.0) -> float:
        if self.visit_count == 0:
            return float("inf")
        if not self.parent:
            return self.value
        return self.value + exploration_constant * math.sqrt(
            math.log(self.parent.visit_count) / self.visit_count
        )


class LanguageAgentTreeSearch:
    """Orchestrates Monte Carlo Tree Search with LLMs and tool execution."""

    def __init__(
        self,
        cognitive_loop: Any,
        max_iterations: int = 3,
        exploration_constant: float = 1.0,
        critic_threshold: float = 0.7,
    ) -> None:
        self.loop = cognitive_loop
        self.max_iterations = max_iterations
        self.exploration_constant = exploration_constant
        self.critic_threshold = critic_threshold

    async def _run_git(self, *args, allow_fail=False) -> str:
        from silex.utils.config import WORKSPACE_DIR
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(WORKSPACE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0 and not allow_fail:
            log.warning(f"Git command 'git {' '.join(args)}' failed: {stderr.decode()}")
        return stdout.decode().strip()

    async def search(
        self,
        user_input: str,
        system_prompt: str,
        images: Optional[List[dict]] = None,
        target_model: Optional[str] = None,
        status_callback: Optional[callable] = None,
        event_emitter: Optional[callable] = None,
        turn_emitter: Optional[Any] = None,
        executed_tool_ids: Optional[List[str]] = None,
    ) -> CognitiveResponse:
        """
        Execute LATS to find the best response by exploring decision branches.
        """
        log.info("Initializing LATS Tree Search...")
        if status_callback:
            status_callback("[bright_cyan]  Initializing Tree Search (LATS)...[/]")

        root_id = str(uuid.uuid4())
        
        is_git = await self._run_git("rev-parse", "--is-inside-work-tree", allow_fail=True)
        is_git_repo = is_git.strip() == "true"

        orig_branch = ""
        lats_branch = ""
        has_stash = False
        root_commit_hash = ""

        if is_git_repo:
            orig_branch = await self._run_git("--no-pager", "rev-parse", "--abbrev-ref", "HEAD")
            lats_branch = f"lats_temp_{root_id}"
            
            status_out = await self._run_git("status", "--porcelain", allow_fail=True)
            has_stash = bool(status_out)
            if has_stash:
                await self._run_git("stash", "push", "-u", "-m", f"lats_pre_stash_{root_id}")
                
            await self._run_git("checkout", "-b", "--", lats_branch, allow_fail=True)
            root_commit_hash = await self._run_git("--no-pager", "rev-parse", "HEAD")

        best_node = None
        try:
            best_node = await self._search_internal(
                user_input, system_prompt, images, target_model,
                status_callback, event_emitter, turn_emitter,
                executed_tool_ids, root_id, root_commit_hash, is_git_repo
            )
            return self._construct_response(best_node)
        finally:
            if is_git_repo:
                await self._run_git("checkout", "--", orig_branch, allow_fail=True)
                if best_node and best_node.commit_hash:
                    await self._run_git("checkout", "--", best_node.commit_hash, allow_fail=True)
                    await self._run_git("symbolic-ref", "HEAD", f"refs/heads/{orig_branch}", allow_fail=True)
                await self._run_git("branch", "-D", "--", lats_branch, allow_fail=True)
                if has_stash:
                    await self._run_git("stash", "pop", allow_fail=True)

    async def _search_internal(
        self,
        user_input: str,
        system_prompt: str,
        images: Optional[List[dict]],
        target_model: Optional[str],
        status_callback: Optional[callable],
        event_emitter: Optional[callable],
        turn_emitter: Optional[Any],
        executed_tool_ids: Optional[List[str]],
        root_id: str,
        root_commit_hash: str,
        is_git_repo: bool
    ) -> LATSNode:

        with tracer.start_as_current_span("llm_pass_1"):
            cognitive = await self.loop.llm.think(
                system_prompt, user_input, images=images, model_override=target_model
            )

        root = LATSNode(
            node_id=root_id,
            parent=None,
            reasoning=cognitive.reasoning,
            response=cognitive.response,
            tool_calls=cognitive.tool_calls,
            depth=0,
        )

        # Execute root tools if planned
        all_tool_ids = []
        if root.tool_calls:
            if status_callback:
                status_callback(
                    f"[magenta]  Root Node: Executing {len(root.tool_calls)} tools...[/]"
                )
            with tracer.start_as_current_span("tool_execution"):
                obs_text, any_failures, tool_results, tool_ids = await self.loop._execute_tools(
                    root.tool_calls,
                    status_callback,
                    execution_mode="interactive",
                    event_emitter=event_emitter,
                    turn_emitter=turn_emitter,
                )
            root.observation = obs_text
            all_tool_ids.extend(tool_ids)
            if executed_tool_ids is not None:
                executed_tool_ids.extend(tool_ids)
            
            # Redraft to incorporate tool results
            if status_callback:
                status_callback("[bright_cyan]  Root Node: Re-drafting response...[/]")
            redraft_prompt = system_prompt + (
                "\n\n═══════════════════════════════════════════════════════════\n"
                "TOOL EXECUTION RESULTS\n"
                "═══════════════════════════════════════════════════════════\n"
                f"{obs_text}\n\n"
                "Incorporate these facts into your final response."
            )
            try:
                cognitive = await self.loop.llm.think(
                    redraft_prompt, user_input, model_override=target_model
                )
                root.response = cognitive.response
                root.reasoning = cognitive.reasoning
            except Exception as e:
                log.warning("LATS: Root node LLM generation failed after retries: %s", e)
                root.response = "Generation failed due to malformed payload."
                root.reasoning = "JSON decoding failed."
                root.is_acceptable = False
                root.critic_score = 0.0

        # Evaluate root node
        if status_callback:
            status_callback("[bright_cyan]  Root Node: Running quality evaluation...[/]")
        
        # Grounding cross-reference
        grounding_memories = await self.loop.memory.retrieve_context(query=user_input)
        memory_nodes = [m.content for m in grounding_memories[:8]]
        
        system_context = "Evaluate the response for logical coherence."
        if root.observation:
            system_context += f"\n\nTOOL EXECUTION RESULTS:\n{root.observation}"

        with tracer.start_as_current_span("critic_evaluation"):
            critique = await self.loop.critic.critique(
                user_input=user_input,
                system_context=system_context,
                draft_response=root.response,
                draft_reasoning=root.reasoning,
                memory_nodes=memory_nodes,
            )

        geo_score = self.loop.critic.geometric_score(
            critique.scores.accuracy, critique.scores.depth, critique.scores.honesty
        )
        root.critic_score = geo_score
        root.is_acceptable = critique.is_acceptable
        root.feedback = critique.feedback

        # Root node commit hash
        root.commit_hash = root_commit_hash
        if root.tool_calls:
            try:
                await self._run_git("add", "-A")
                await self._run_git("commit", "-m", f"LATS Root Node {root_id}")
                root.commit_hash = await self._run_git("--no-pager", "rev-parse", "HEAD")
            except Exception as e:
                log.warning("LATS: Failed to commit root tools changes: %s", e)

        # Register root node in DB
        await self._register_node_to_db(root, "decision" if root.tool_calls else "hypothesis")
        root.visit_count = 1
        root.value_sum = geo_score

        # Link executed tools to the resulting root node
        if all_tool_ids and self.loop.session.current:
            for tid in all_tool_ids:
                await self.loop.causal_kg.register_edge(CausalEdge.new(
                    source_node_id=tid,
                    target_node_id=root.node_id,
                    relation_type="triggered_by",
                    weight=geo_score
                ))

        # Check early termination
        if root.is_acceptable or root.critic_score >= self.critic_threshold:
            log.info("LATS: Root node acceptable. Terminating search.")
            if status_callback:
                status_callback("[green]  ✔ Optimal response found at root node.[/]")
            return root

        # 2. Search iterations
        best_node = root
        for iteration in range(1, self.max_iterations + 1):
            log.info(f"LATS: Starting search iteration {iteration}/{self.max_iterations}")
            if status_callback:
                status_callback(f"[bright_cyan]  LATS Iteration {iteration}/{self.max_iterations}...[/]")

            # Selection
            selected = root
            while selected.children:
                selected = max(
                    selected.children,
                    key=lambda node: node.ucb1(self.exploration_constant),
                )
            
            log.info(f"LATS: Selected node {selected.node_id[:8]} at depth {selected.depth}")

            # Expansion (generate 2 candidate alternative actions)
            if status_callback:
                status_callback(f"[bright_cyan]  LATS: Expanding node {selected.node_id[:8]}...[/]")
            
            candidates = await self._generate_candidates(
                selected, user_input, system_prompt, target_model, num_candidates=2
            )

            for idx, candidate in enumerate(candidates, 1):
                child_id = str(uuid.uuid4())
                child = LATSNode(
                    node_id=child_id,
                    parent=selected,
                    reasoning=candidate.reasoning,
                    response=candidate.response,
                    tool_calls=candidate.tool_calls,
                    depth=selected.depth + 1,
                )

                # 1. Reset/Checkout to parent node's commit hash
                parent_hash = selected.commit_hash or root_commit_hash
                try:
                    await self._run_git("reset", "--hard", "--", parent_hash)
                    await self._run_git("clean", "-fd")
                except Exception as e:
                    log.warning("LATS: Failed to reset workspace to parent state: %s", e)

                # Simulation / Evaluation: Execute tool calls if any
                child_tool_ids = []
                if child.tool_calls:
                    if status_callback:
                        status_callback(
                            f"[magenta]  LATS Branch {idx}: Executing {len(child.tool_calls)} tools...[/]"
                        )
                    obs_text, any_failures, tool_results, tool_ids = await self.loop._execute_tools(
                        child.tool_calls,
                        status_callback,
                        execution_mode="interactive",
                        event_emitter=event_emitter,
                        turn_emitter=turn_emitter,
                    )
                    child.observation = obs_text
                    child_tool_ids.extend(tool_ids)
                    if executed_tool_ids is not None:
                        executed_tool_ids.extend(tool_ids)

                # 2. Commit the changes and store the new commit hash in child.commit_hash
                try:
                    await self._run_git("add", "-A")
                    await self._run_git("commit", "-m", f"LATS Node {child_id}")
                    child.commit_hash = await self._run_git("--no-pager", "rev-parse", "HEAD")
                except Exception as e:
                    log.warning("LATS: Failed to commit child node changes: %s", e)
                    child.commit_hash = parent_hash

                    # Redraft to incorporate tool results
                    redraft_prompt = system_prompt + (
                        f"\n\n═══════════════════════════════════════════════════════════\n"
                        f"PARENT CRITIQUE FEEDBACK:\n{selected.feedback}\n"
                        f"═══════════════════════════════════════════════════════════\n"
                        f"TOOL EXECUTION RESULTS:\n{obs_text}\n\n"
                        f"Incorporate these facts into your final response."
                    )
                    try:
                        cognitive_redraft = await self.loop.llm.think(
                            redraft_prompt, user_input, model_override=target_model
                        )
                        child.response = cognitive_redraft.response
                        child.reasoning = cognitive_redraft.reasoning
                    except Exception as e:
                        log.warning("LATS: Child node LLM generation failed after retries: %s", e)
                        child.response = "Generation failed due to malformed payload."
                        child.reasoning = "JSON decoding failed."

                # Critique child
                child_context = "Evaluate the response for logical coherence."
                if child.observation:
                    child_context += f"\n\nTOOL EXECUTION RESULTS:\n{child.observation}"
                
                child_critique = await self.loop.critic.critique(
                    user_input=user_input,
                    system_context=child_context,
                    draft_response=child.response,
                    draft_reasoning=child.reasoning,
                    memory_nodes=memory_nodes,
                )

                child_geo = self.loop.critic.geometric_score(
                    child_critique.scores.accuracy,
                    child_critique.scores.depth,
                    child_critique.scores.honesty,
                )
                child.critic_score = child_geo
                child.is_acceptable = child_critique.is_acceptable
                child.feedback = child_critique.feedback

                # Register child node and edge in database
                node_type = "decision" if child.tool_calls else "hypothesis"
                if not child.is_acceptable and child.critic_score < 0.4:
                    node_type = "dead_end"
                
                await self._register_node_to_db(child, node_type)
                
                # Register edge
                relation = "triggered_by"
                if node_type == "dead_end":
                    relation = "caused_failure_in"
                await self.loop.causal_kg.register_edge(CausalEdge.new(
                    source_node_id=selected.node_id,
                    target_node_id=child.node_id,
                    relation_type=relation,
                    weight=child.critic_score
                ))

                # Link tool logs to child
                if child_tool_ids and self.loop.session.current:
                    for tid in child_tool_ids:
                        await self.loop.causal_kg.register_edge(CausalEdge.new(
                            source_node_id=tid,
                            target_node_id=child.node_id,
                            relation_type="triggered_by",
                            weight=child.critic_score
                        ))

                # Initialize visit count
                child.visit_count = 1
                child.value_sum = child.critic_score

                selected.children.append(child)

                # Update best node
                if child.critic_score > best_node.critic_score:
                    best_node = child

                if child.is_acceptable:
                    log.info(f"LATS: Found acceptable node {child.node_id[:8]}! Stopping search.")
                    break

            # Backpropagation
            curr = selected
            while curr:
                curr.visit_count += 1
                curr.value_sum += best_node.critic_score
                curr = curr.parent

            if best_node.is_acceptable:
                break

        log.info(f"LATS Search finished. Best node: {best_node.node_id[:8]} (Score: {best_node.critic_score:.4f})")
        if status_callback:
            status_callback(f"[green]  ✔ LATS finished. Best branch score: {best_node.critic_score:.4f}[/]")

        return best_node

    def _construct_response(self, best_node: LATSNode) -> CognitiveResponse:
        return CognitiveResponse(
            reasoning=best_node.reasoning,
            working_scratchpad=f"LATS Best Node: {best_node.node_id[:8]} | Score: {best_node.critic_score:.3f}",
            response=best_node.response,
            new_memories=[],
            goal_updates=[],
            self_reflection=best_node.feedback,
            confidence=best_node.critic_score,
            uncertainty_flags=[] if best_node.is_acceptable else ["suboptimal_critic_score"],
            uncertainty_tracking=[],
            causal_observations=[],
            contradictions_detected=[],
            hypotheses=[],
            hypothesis_resolutions=[],
            tool_calls=best_node.tool_calls,
        )

    async def _generate_candidates(
        self,
        node: LATSNode,
        user_input: str,
        system_prompt: str,
        target_model: Optional[str],
        num_candidates: int = 2,
    ) -> List[CognitiveResponse]:
        """Ask LLM to generate alternative corrected actions based on parent feedback."""
        candidates = []
        
        # Build correction instruction
        history_context = (
            f"The previous draft was rejected by the critic. "
            f"Critic score: {node.critic_score:.2f} | Feedback: {node.feedback}\n"
            f"Your previous response was:\n{node.response}\n\n"
        )
        if node.observation:
            history_context += f"The executed tools returned:\n{node.observation}\n\n"

        tasks = []
        for i in range(num_candidates):
            # We vary temperature and instruction slightly for diversity
            temp_mod = 0.5 + (i * 0.2)
            expansion_prompt = system_prompt + (
                "\n\n═══════════════════════════════════════════════════════════\n"
                "LATS TREE SEARCH: CANDIDATE CORRECTION PATH\n"
                "═══════════════════════════════════════════════════════════\n"
                f"{history_context}"
                f"Propose an alternative approach or next execution step to correct the draft. "
                f"If you need to use tools, generate `tool_calls`. Otherwise, output a refined response. "
                f"Do not repeat the exact same tool parameters or reasoning as the failed attempt."
            )
            tasks.append(
                self.loop.llm.think(
                    expansion_prompt,
                    user_input,
                    model_override=target_model,
                    temperature=temp_mod,
                )
            )
        
        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                log.error(f"Failed to generate candidate {i}: {res}")
            else:
                candidates.append(res)
                
        # Fallback if no candidates were generated
        if not candidates:
            try:
                fallback = await self.loop.llm.think(
                    system_prompt + "\n\nProvide a corrected response.", user_input, model_override=target_model
                )
                candidates.append(fallback)
            except Exception as e:
                log.error(f"Fallback candidate generation failed: {e}")
            
        return candidates

    async def _register_node_to_db(self, node: LATSNode, node_type: str) -> None:
        """Register the node in the SQLite database causal graph."""
        if not self.loop.session.current:
            return

        try:
            epistemic_node = EpistemicNode(
                node_id=node.node_id,
                session_id=self.loop.session.current.id,
                run_id=self.loop.session.current.id,
                type=node_type,
                content=f"LATS Node (Depth {node.depth}, Score {node.critic_score:.2f}): {node.response[:300]}",
                provenance="tree_search",
                metadata={"critic_feedback": node.feedback, "ucb1": node.ucb1()},
                timestamp=time.time(),
            )
            await self.loop.causal_kg.register_node(epistemic_node)
        except Exception as e:
            log.warning(f"Failed to log LATS node to causal graph: {e}")
