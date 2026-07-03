"""
Central Coordinator for Autonomous Self-Evolution (Phase 7.5).

Orchestrates Trajectory Optimization, Metacognitive Self-Modification (HyperAgent),
Runtime test sandboxes (TDD Loops), and Skill Distillation (A-MAC).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from silex.storage.database import Database
from silex.llm.base import SupportsLLM
from silex.utils.logger import setup_logger

from silex.evolution.trajectory_optimizer import TrajectoryOptimizer
from silex.evolution.self_modification import SelfModificationEngine
from silex.evolution.tdd_loops import RuntimeExtensionEngine
from silex.evolution.admission_control import SkillAdmissionController

log = setup_logger("silex.evolution.core")

# ---------------------------------------------------------------------------
# Structured Output Schema for Skill Synthesis
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field

class SkillSynthesisResponse(BaseModel):
    rationale: str = Field(..., description="Explanation of why this skill is structured this way")
    markdown_instructions: str = Field(..., description="The complete instruction manual for this skill in Markdown format")


# ---------------------------------------------------------------------------
# SelfEvolutionCoordinator
# ---------------------------------------------------------------------------

class SelfEvolutionCoordinator:
    """
    Integrates all Phase 7 pillars:
      - Trajectory Optimization (Revision, Recombination, Refinement)
      - Self-Modification (Bandit Search & Mutation)
      - TDD Loop Sandboxes (Isolated Execution & Feedback Correction)
      - Skill Distillation (A-MAC Admission & Export)
    """

    def __init__(self, db: Database, llm_client: SupportsLLM, evolution_dir: Path | str | None = None):
        self.db = db
        self.llm_client = llm_client

        if evolution_dir is None:
            self.evolution_dir = Path("~/.kinthic/evolution").expanduser()
        else:
            self.evolution_dir = Path(evolution_dir)
        self.evolution_dir.mkdir(parents=True, exist_ok=True)

        self.optimizer = TrajectoryOptimizer(db, llm_client)
        self.self_mod = SelfModificationEngine(base_dir=self.evolution_dir)
        self.tdd = RuntimeExtensionEngine(sandbox_dir=self.evolution_dir / "sandbox")
        self.admission = SkillAdmissionController(db, skills_dir=self.evolution_dir / "skills")

    async def evolve_trajectory_revision(self, trajectory_id: str) -> dict[str, Any]:
        """Runs the Revision operator to critique and adjust step categories."""
        return await self.optimizer.run_revision(trajectory_id)

    async def recombine_paths(self, t1_id: str, t2_id: str) -> str | None:
        """Runs the Recombination operator to splice successful pathways at crossover steps."""
        return await self.optimizer.run_recombination(t1_id, t2_id)

    async def refine_path(self, trajectory_id: str) -> str:
        """Runs the Refinement operator to prune redundant actions and compress outputs."""
        return await self.optimizer.run_refinement(trajectory_id)

    async def propose_and_validate_mutation(
        self,
        parent_id: str,
        file_to_mutate: str | Path,
        guidance: str,
        test_file: str | Path
    ) -> tuple[bool, str, str]:
        """
        HyperAgent loop:
          1. Generates code mutation.
          2. Sets up isolated sandbox directory.
          3. Splicing target files under default names to bypass test import paths.
          4. Runs TDD Loop (up to 3 correction rounds).
          5. Records feedback in UCB bandit manifest.
        """
        file_path = Path(file_to_mutate).resolve()
        test_path = Path(test_file).resolve()

        if not self.self_mod.is_path_safe(file_path):
            raise PermissionError(f"Access denied to modify sacred path: {file_path}")

        # 1. Propose mutation code variant via LLM
        variant_id = await self.self_mod.propose_mutation(
            parent_variant_id=parent_id,
            file_to_mutate=file_path,
            prompt_guidance=guidance,
            llm_client=self.llm_client
        )

        variant_record = self.self_mod.manifest["variants"][variant_id]
        variant_source_path = Path(variant_record["path"])

        # 2. Setup sandboxed execution environment
        sandbox_run_dir = self.tdd.sandbox_dir / f"run_{variant_id}"
        sandbox_run_dir.mkdir(parents=True, exist_ok=True)

        # Copy mutated code to the sandbox renaming it back to the original filename
        sandbox_target_path = sandbox_run_dir / file_path.name
        shutil.copy2(variant_source_path, sandbox_target_path)

        # Copy the test file to the sandbox directory
        sandbox_test_path = sandbox_run_dir / test_path.name
        shutil.copy2(test_path, sandbox_test_path)

        # Copy other sibling files in same package to resolve sandbox imports if present
        for sibling in file_path.parent.glob("*.py"):
            if sibling.name != file_path.name:
                shutil.copy2(sibling, sandbox_run_dir / sibling.name)

        log.info(f"Isolated sandbox prepared for variant {variant_id} at {sandbox_run_dir}")

        # 3. Run closed-loop TDD validations
        success, test_msg, final_code = await self.tdd.run_tdd_loop(
            file_to_mutate=sandbox_target_path,
            test_file=sandbox_test_path,
            prompt_guidance=guidance,
            llm_client=self.llm_client,
            max_iterations=3
        )

        # 4. Copy back corrected code from sandbox to variants folder
        shutil.copy2(sandbox_target_path, variant_source_path)

        # 5. Record feedback in UCB bandit manifest
        score = 1.0 if success else 0.0
        self.self_mod.record_feedback(variant_id, score)

        # Clean up isolated sandbox run directory
        try:
            shutil.rmtree(sandbox_run_dir)
        except Exception as e:
            log.warning(f"Failed to cleanup sandbox run directory {sandbox_run_dir}: {e}")

        return success, variant_id, test_msg

    async def distill_trajectory_to_skill(
        self,
        trajectory_id: str,
        category: str,
        skill_name: str,
        description: str,
        threshold: float = 0.70
    ) -> tuple[bool, float]:
        """
        Collects actions from successful trajectories, prompts LLM to format
        them as structured instruction manuals, and runs A-MAC admission checks.
        """
        log.info(f"Distilling trajectory {trajectory_id} to skill: {skill_name}")
        
        # 1. Retrieve steps from database
        steps = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id,)
        )
        if not steps:
            raise ValueError(f"No execution steps found for trajectory: {trajectory_id}")

        # 2. Format execution path summary
        path_summary = []
        for s in steps:
            path_summary.append({
                "step_order": s["step_order"],
                "action": s["action_name"],
                "input": s["tool_input"],
                "output": s["execution_output"][:400] + ("..." if len(s["execution_output"]) > 400 else "")
            })

        # 3. Prompt LLM to synthesize Markdown instructions
        system_prompt = (
            "You are Kinthic's Skill Distillation and Memory Synthesis Engine.\n"
            "Review the successful execution path (actions, inputs, outputs) of a completed task "
            "and synthesize a reusable markdown-formatted instruction skill manual.\n"
            "This manual should be structured, concise, detail all prerequisites, steps, warnings, "
            "and serve as a robust reference guide for other agents to execute this task correctly."
        )

        user_input = json.dumps({
            "skill_name": skill_name,
            "description": description,
            "category": category,
            "trajectory_steps": path_summary
        }, indent=2)

        synth_result: SkillSynthesisResponse = await self.llm_client.complete_json(
            schema=SkillSynthesisResponse,
            system_prompt=system_prompt,
            user_input=user_input,
            temperature=0.3
        )

        # 4. Filter and gate via A-MAC Admission Controller
        # Use a high baseline utility score since this trajectory was successful (is_success = 1)
        success, score = await self.admission.admit_skill(
            skill_name=skill_name,
            category=category,
            description=description,
            content=synth_result.markdown_instructions,
            utility_score=1.0,
            confidence_score=1.0,
            type_prior=0.8,
            origin_trajectory_id=trajectory_id,
            threshold=threshold
        )

        return success, score
