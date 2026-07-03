"""
Genesis Skill Synthesizer (Phase 1).

Monitors successful trajectories and abstracts them into reusable, parameterized skills.
"""

from __future__ import annotations

import os
import time
import json
from pathlib import Path
from pydantic import BaseModel, Field

from silex.storage.database import Database
from silex.llm.base import SupportsLLM
from silex.world.graph import KnowledgeGraph
from silex.utils.config import KRONOS_HOME
from silex.utils.logger import setup_logger

log = setup_logger("silex.autonomy.skill_synthesizer")


class SkillSynthesisResult(BaseModel):
    skill_name: str = Field(..., description="A short, descriptive, lower_snake_case name for the skill.")
    description: str = Field(..., description="A clear description of what the skill does.")
    skill_md: str = Field(..., description="The complete SKILL.md file contents including YAML frontmatter.")
    python_script: str = Field(..., description="The full parameterized python script content to execute the skill. Leave empty if no script is needed.")
    dependencies: list[str] = Field(default_factory=list, description="List of pip dependencies required by the script.")


class PreferenceValidationResult(BaseModel):
    is_safe: bool = Field(..., description="True if the skill is safe and doesn't contradict user preferences.")
    contradiction_reason: str = Field(..., description="Explanation if a contradiction was found, else empty.")


class GenesisSynthesizer:
    """
    Background worker that abstracts successful task trajectories into reusable skills.
    """

    def __init__(self, db: Database, llm: SupportsLLM, kg: KnowledgeGraph):
        self.db = db
        self.llm = llm
        self.kg = kg

    async def run(self) -> str | None:
        """
        Runs one cycle of the skill synthesizer.
        Finds one un-synthesized successful trajectory and processes it.
        """
        log.info("GenesisSynthesizer: Checking for new successful trajectories...")
        
        # 1. Fetch un-synthesized trajectory
        row = await self.db.fetch_one(
            """
            SELECT t.* FROM trajectories t
            LEFT JOIN synthesized_trajectories st ON t.trajectory_id = st.trajectory_id
            WHERE t.is_success = 1 AND st.trajectory_id IS NULL AND t.total_tokens > 0
            ORDER BY t.timestamp ASC LIMIT 1
            """
        )
        if not row:
            return None
            
        trajectory_id = row["trajectory_id"]
        task_desc = row["task_description"]
        
        # Fetch steps
        steps = await self.db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (trajectory_id,)
        )
        
        if len(steps) < 2:
            # Too short to be a meaningful skill, skip it
            await self._mark_synthesized(trajectory_id, "skipped_too_short")
            return None
            
        log.info(f"GenesisSynthesizer: Processing trajectory {trajectory_id} ('{task_desc}')")
        
        steps_summary = []
        for s in steps:
            steps_summary.append({
                "action": s["action_name"],
                "input": s["tool_input"],
                "output": s["execution_output"][:500] + ("..." if len(s["execution_output"]) > 500 else "")
            })
            
        # 2. Extract User Preferences / World Model for Contradiction Checking
        prefs = await self._get_user_preferences()
        
        # 3. Call LLM to synthesize the skill
        system_prompt = (
            "You are Kronos's Genesis Skill Synthesizer.\n"
            "Your job is to review a successful multi-step workflow (a trajectory) and abstract it into a reusable Skill.\n"
            "A Kronos Skill consists of a SKILL.md file (which teaches the agent how to use it) and optionally a Python script "
            "that the agent can execute. The script must be parameterized so it works for similar future tasks.\n"
            "If the workflow relies heavily on standard terminal commands, you can just write a SKILL.md that explains "
            "the terminal commands to use. If it requires complex logic, write a Python script.\n\n"
            "SKILL.md FORMAT MUST INCLUDE YAML FRONTMATTER:\n"
            "---\nname: skill_name\ndescription: Brief description\nversion: 1.0.0\nauthor: genesis\n---\n"
            "# Usage\n...\n"
        )
        
        user_input = json.dumps({
            "task": task_desc,
            "steps": steps_summary,
            "user_preferences": prefs
        }, indent=2)
        
        try:
            synthesis: SkillSynthesisResult = await self.llm.complete_json(
                schema=SkillSynthesisResult,
                system_prompt=system_prompt,
                user_input=user_input,
                temperature=0.2
            )
            
            # 4. Validate against Contradictions
            if not await self._validate_skill(synthesis, prefs):
                log.warning(f"GenesisSynthesizer: Skill {synthesis.skill_name} failed preference validation. Discarding.")
                await self._mark_synthesized(trajectory_id, "failed_validation")
                return None
                
            # 5. Write to Disk
            skill_dir = KRONOS_HOME / "skills" / synthesis.skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            
            # Write SKILL.md
            (skill_dir / "SKILL.md").write_text(synthesis.skill_md, encoding="utf-8")
            
            # Write python script if provided
            if synthesis.python_script.strip():
                script_path = skill_dir / f"{synthesis.skill_name}.py"
                script_path.write_text(synthesis.python_script, encoding="utf-8")
                
            # Write dependencies if any
            if synthesis.dependencies:
                (skill_dir / "requirements.txt").write_text("\n".join(synthesis.dependencies), encoding="utf-8")
                
            # 6. Mark as synthesized
            await self._mark_synthesized(trajectory_id, synthesis.skill_name)
            log.info(f"GenesisSynthesizer: Successfully created new skill '{synthesis.skill_name}' from trajectory {trajectory_id}.")
            return synthesis.skill_name
            
        except Exception as e:
            log.error(f"GenesisSynthesizer: Failed to synthesize skill for {trajectory_id}: {e}")
            return None

    async def _get_user_preferences(self) -> str:
        """Extract high-level user preferences from the graph or profile."""
        try:
            row = await self.db.fetch_one("SELECT global_preferences FROM user_profiles WHERE user_id = 'default'")
            if row and row["global_preferences"]:
                return str(row["global_preferences"])
        except Exception:
            pass
        return "No specific preferences recorded."

    async def _validate_skill(self, skill: SkillSynthesisResult, prefs: str) -> bool:
        """Validate that the new skill does not contradict user preferences."""
        prompt = (
            "You are a Safety and Preference Validator.\n"
            "Review the proposed new skill and the user's core preferences.\n"
            "Does this skill violate or contradict any user preferences (e.g. hardcoded paths that are wrong, "
            "using forbidden languages/tools)? If it is safe, return is_safe=true."
        )
        user_in = f"PREFERENCES:\n{prefs}\n\nSKILL NAME:\n{skill.skill_name}\n\nSKILL_MD:\n{skill.skill_md}\n\nSCRIPT:\n{skill.python_script}"
        
        try:
            val: PreferenceValidationResult = await self.llm.complete_json(
                schema=PreferenceValidationResult,
                system_prompt=prompt,
                user_input=user_in,
                temperature=0.0
            )
            if not val.is_safe:
                log.warning(f"Skill validation contradiction: {val.contradiction_reason}")
            return val.is_safe
        except Exception:
            return True # Fail open on validation error

    async def _mark_synthesized(self, trajectory_id: str, skill_name: str) -> None:
        await self.db.execute(
            "INSERT INTO synthesized_trajectories (trajectory_id, skill_name, synthesized_at) VALUES (?, ?, ?)",
            (trajectory_id, skill_name, time.time())
        )
