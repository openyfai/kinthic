"""
Trajectory-Level Optimizer for Kinthic (Phase 7.1).

Implements Revision, Recombination, and Refinement on past execution trajectories.
"""

from __future__ import annotations

import json
import uuid
import time
from typing import Any
from pydantic import BaseModel, Field

from silex.storage.database import Database
from silex.llm.base import SupportsLLM
from silex.utils.logger import setup_logger

log = setup_logger("silex.evolution.trajectory_optimizer")

# ---------------------------------------------------------------------------
# Structured Output Schemas for LLM
# ---------------------------------------------------------------------------

class StepRevision(BaseModel):
    step_order: int = Field(..., description="The step order index (1-based) to revise")
    revised_category: str = Field(..., description="Must be one of 'decision', 'hypothesis', 'fact', 'dead_end'")
    reasoning: str = Field(..., description="Detailed explanation for this category revision")

class TrajectoryRevisionResult(BaseModel):
    critique: str = Field(..., description="Reflecting critique on the trajectory failure and error patterns")
    step_revisions: list[StepRevision] = Field(..., description="List of step category adjustments")


class StepRefinement(BaseModel):
    step_order: int = Field(..., description="The step order index (1-based) to refine")
    compressed_output: str = Field(..., description="Summarized/compressed output maintaining critical debug info")
    token_saved_estimate: int = Field(..., description="Estimated tokens saved by compressing this output")

class TrajectoryRefinementResult(BaseModel):
    rationale: str = Field(..., description="Explanation of why certain steps were compressed")
    step_refinements: list[StepRefinement] = Field(..., description="List of step payload compressions")


# ---------------------------------------------------------------------------
# TrajectoryOptimizer Class
# ---------------------------------------------------------------------------

class TrajectoryOptimizer:
    """
    Optimizes agent execution paths by analyzing past trajectories.
    
    Operations:
      - Revision: Critique failures and correct epistemic step categorizations.
      - Recombination: Combine successful path segments from different runs at crossover points.
      - Refinement: Prune duplicate consecutive tool calls and compress token footprints.
    """

    def __init__(self, db: Database, llm_client: SupportsLLM):
        self.db = db
        self.llm_client = llm_client

    async def run_revision(self, trajectory_id: str) -> dict[str, Any]:
        """
        Revision operator:
        Identifies failing/dead-end steps in a trajectory, calls the LLM to generate
        a reflecting critique, and updates the step categories in the database.
        """
        log.info(f"Running Revision on trajectory: {trajectory_id}")
        
        # 1. Fetch trajectory and steps
        trajectory = await self.db.fetch_one(
            "SELECT * FROM trajectories WHERE trajectory_id = ?",
            (trajectory_id,)
        )
        if not trajectory:
            raise ValueError(f"Trajectory {trajectory_id} not found.")

        steps = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id,)
        )
        
        # 2. Format steps for LLM prompt
        steps_summary = []
        for s in steps:
            steps_summary.append({
                "step_order": s["step_order"],
                "action_name": s["action_name"],
                "tool_input": s["tool_input"],
                "execution_output": s["execution_output"][:300] + ("..." if len(s["execution_output"]) > 300 else ""),
                "current_category": s["epistemic_category"]
            })
            
        system_prompt = (
            "You are Kinthic's Metacognitive Revision Engine.\n"
            "Your task is to review a series of execution steps from a task, locate where errors or "
            "dead-ends occurred, write a critique summarizing the failure mode, and propose revised "
            "epistemic categories for the steps. Step categories must be exactly one of: "
            "'decision', 'hypothesis', 'fact', 'dead_end'.\n"
            "If a step was a mistake or led to a dead-end, its revised category should be 'dead_end'."
        )
        
        user_input = json.dumps({
            "task_description": trajectory["task_description"],
            "is_success": bool(trajectory["is_success"]),
            "steps": steps_summary
        }, indent=2)
        
        # 3. Call LLM for structured revision advice
        revision_data: TrajectoryRevisionResult = await self.llm_client.complete_json(
            schema=TrajectoryRevisionResult,
            system_prompt=system_prompt,
            user_input=user_input,
            temperature=0.2
        )
        
        # 4. Commit category updates to database
        async with self.db.transaction():
            for rev in revision_data.step_revisions:
                if rev.revised_category in ('decision', 'hypothesis', 'fact', 'dead_end'):
                    await self.db.execute(
                        """
                        UPDATE trajectory_steps
                        SET epistemic_category = ?
                        WHERE trajectory_id = ? AND step_order = ?
                        """,
                        (rev.revised_category, trajectory_id, rev.step_order)
                    )
                    log.debug(f"Mutated step {rev.step_order} to category {rev.revised_category}")

        log.info(f"Revision complete for trajectory: {trajectory_id}")
        return {
            "trajectory_id": trajectory_id,
            "critique": revision_data.critique,
            "step_revisions": [r.model_dump() for r in revision_data.step_revisions]
        }

    async def run_recombination(self, trajectory_id_1: str, trajectory_id_2: str) -> str | None:
        """
        Recombination operator:
        Finds overlapping/matching steps between two successful trajectories (crossover points)
        and splices them to form a new combined trajectory, inserting it into the database.
        """
        log.info(f"Running Recombination between {trajectory_id_1} and {trajectory_id_2}")
        
        # 1. Fetch trajectories and steps
        t1 = await self.db.fetch_one("SELECT * FROM trajectories WHERE trajectory_id = ?", (trajectory_id_1,))
        t2 = await self.db.fetch_one("SELECT * FROM trajectories WHERE trajectory_id = ?", (trajectory_id_2,))
        
        if not t1 or not t2:
            log.warning("One or both trajectories not found for recombination.")
            return None
            
        if not t1["is_success"] or not t2["is_success"]:
            log.warning("Recombination expects successful trajectories as parent paths.")
            return None
            
        steps1 = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id_1,)
        )
        steps2 = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id_2,)
        )
        
        # 2. Find crossover points (steps with identical action_name)
        crossover_points = []
        for i, s1 in enumerate(steps1):
            for j, s2 in enumerate(steps2):
                if s1["action_name"] == s2["action_name"] and s1["action_name"] != "initialize":
                    crossover_points.append((i, j, s1["action_name"]))
                    
        if not crossover_points:
            log.info("No viable crossover actions found between the two trajectories.")
            return None
            
        # Select the first crossover point for recombination
        idx1, idx2, action = crossover_points[0]
        log.info(f"Crossover point identified at action '{action}' (T1 index {idx1}, T2 index {idx2})")
        
        # Combine: T1 up to crossover index (inclusive) + T2 from crossover index + 1 (exclusive) to end
        combined_steps = []
        for order, s in enumerate(steps1[:idx1 + 1], start=1):
            combined_steps.append({
                "step_order": order,
                "action_name": s["action_name"],
                "tool_input": s["tool_input"],
                "execution_output": s["execution_output"],
                "epistemic_category": s["epistemic_category"],
                "latency_ms": s["latency_ms"],
                "token_usage": s["token_usage"]
            })
            
        start_order = len(combined_steps) + 1
        for order, s in enumerate(steps2[idx2 + 1:], start=start_order):
            combined_steps.append({
                "step_order": order,
                "action_name": s["action_name"],
                "tool_input": s["tool_input"],
                "execution_output": s["execution_output"],
                "epistemic_category": s["epistemic_category"],
                "latency_ms": s["latency_ms"],
                "token_usage": s["token_usage"]
            })
            
        # Calculate new metadata
        new_id = f"recomb_{uuid.uuid4().hex[:8]}"
        new_desc = f"Recombined trajectory from {trajectory_id_1} and {trajectory_id_2} (crossover: {action})"
        cumulative_latency = sum(s["latency_ms"] for s in combined_steps) / 1000.0
        total_tokens = sum(s["token_usage"] for s in combined_steps)
        
        # 3. Save recombined trajectory to DB
        async with self.db.transaction():
            await self.db.execute(
                """
                INSERT INTO trajectories (
                    trajectory_id, task_description, is_success,
                    cumulative_latency, total_tokens, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_id, new_desc, 1, cumulative_latency, total_tokens, time.time())
            )
            
            for s in combined_steps:
                await self.db.execute(
                    """
                    INSERT INTO trajectory_steps (
                        trajectory_id, step_order, action_name, tool_input,
                        execution_output, epistemic_category, latency_ms, token_usage
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id, s["step_order"], s["action_name"], s["tool_input"],
                        s["execution_output"], s["epistemic_category"], s["latency_ms"], s["token_usage"]
                    )
                )
                
        log.info(f"Successfully created recombined trajectory: {new_id}")
        return new_id

    async def run_refinement(self, trajectory_id: str) -> str:
        """
        Refinement operator:
        1. Prunes duplicate consecutive tool calls with identical inputs.
        2. Compresses token-heavy execution outputs using LLM summarization.
        Updates the database with refined steps and re-computes total token usage.
        """
        log.info(f"Running Refinement on trajectory: {trajectory_id}")
        
        # 1. Fetch trajectory and steps
        trajectory = await self.db.fetch_one("SELECT * FROM trajectories WHERE trajectory_id = ?", (trajectory_id,))
        if not trajectory:
            raise ValueError(f"Trajectory {trajectory_id} not found.")
            
        steps = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id,)
        )
        
        # 2. Heuristic prune: Remove consecutive duplicate tool invocations
        pruned_steps = []
        for s in steps:
            if pruned_steps:
                last = pruned_steps[-1]
                if last["action_name"] == s["action_name"] and last["tool_input"] == s["tool_input"]:
                    log.info(f"Pruning duplicate consecutive call to tool: {s['action_name']}")
                    continue
            pruned_steps.append({
                "step_order": s["step_order"],
                "action_name": s["action_name"],
                "tool_input": s["tool_input"],
                "execution_output": s["execution_output"],
                "epistemic_category": s["epistemic_category"],
                "latency_ms": s["latency_ms"],
                "token_usage": s["token_usage"]
            })
            
        # 3. LLM compress: Identify steps with large token/output payloads and compress them
        heavy_steps = [s for s in pruned_steps if len(s["execution_output"]) > 500]
        if heavy_steps:
            system_prompt = (
                "You are Kinthic's Token Footprint Refinement Engine.\n"
                "Review the provided verbose execution outputs and produce a compressed/summarized version "
                "for each step, keeping all critical errors, paths, and metadata, but stripping redundant logs."
            )
            
            heavy_summary = [{"step_order": s["step_order"], "output": s["execution_output"]} for s in heavy_steps]
            user_input = json.dumps({"steps_to_compress": heavy_summary}, indent=2)
            
            try:
                refinement_data: TrajectoryRefinementResult = await self.llm_client.complete_json(
                    schema=TrajectoryRefinementResult,
                    system_prompt=system_prompt,
                    user_input=user_input,
                    temperature=0.1
                )
                
                # Apply LLM refinements
                refinement_map = {ref.step_order: ref for ref in refinement_data.step_refinements}
                for s in pruned_steps:
                    if s["step_order"] in refinement_map:
                        ref = refinement_map[s["step_order"]]
                        s["execution_output"] = ref.compressed_output
                        # Subtract estimated saved tokens (safely bounded)
                        s["token_usage"] = max(50, s["token_usage"] - ref.token_saved_estimate)
                        log.debug(f"Compressed output for step {s['step_order']}, saved ~{ref.token_saved_estimate} tokens.")
            except Exception as e:
                log.warning(f"LLM footprint compression failed, falling back to heuristic: {e}")
                # Fallback to simple truncation
                for s in pruned_steps:
                    if len(s["execution_output"]) > 1000:
                        s["execution_output"] = s["execution_output"][:800] + "\n[Truncated by Refinement Heuristic]"
                        s["token_usage"] = int(s["token_usage"] * 0.6)
                        
        # 4. Re-index step orders sequentially and update database
        async with self.db.transaction():
            # Delete old steps
            await self.db.execute(
                "DELETE FROM trajectory_steps WHERE trajectory_id = ?",
                (trajectory_id,)
            )
            
            total_tokens = 0
            cumulative_latency_ms = 0.0
            
            for idx, s in enumerate(pruned_steps, start=1):
                await self.db.execute(
                    """
                    INSERT INTO trajectory_steps (
                        trajectory_id, step_order, action_name, tool_input,
                        execution_output, epistemic_category, latency_ms, token_usage
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trajectory_id, idx, s["action_name"], s["tool_input"],
                        s["execution_output"], s["epistemic_category"], s["latency_ms"], s["token_usage"]
                    )
                )
                total_tokens += s["token_usage"]
                cumulative_latency_ms += s["latency_ms"]
                
            # Update parent trajectory stats
            await self.db.execute(
                """
                UPDATE trajectories
                SET total_tokens = ?, cumulative_latency = ?
                WHERE trajectory_id = ?
                """,
                (total_tokens, cumulative_latency_ms / 1000.0, trajectory_id)
            )
            
        log.info(f"Refinement complete for trajectory: {trajectory_id}")
        return trajectory_id
