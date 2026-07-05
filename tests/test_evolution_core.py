"""
Unit and integration tests for the SelfEvolutionCoordinator (Phase 7.5).
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path

from silex.storage.database import Database
from silex.evolution.core import SelfEvolutionCoordinator, SkillSynthesisResponse
from silex.evolution.self_modification import CodeMutationResponse
from silex.evolution.tdd_loops import TDDCorrectionResponse


class MockLLMCoordinatorClient:
    def __init__(self):
        self.calls = []

    async def complete_json(
        self,
        *,
        schema,
        system_prompt,
        user_input,
        images=None,
        model_override=None,
        temperature=0.7,
        request_kind="chat",
    ):
        self.calls.append((schema, user_input))
        if schema == CodeMutationResponse:
            return CodeMutationResponse(
                rationale="Optimize arithmetic loop",
                mutated_code="def run_computation(a, b):\n    return a + b\n"
            )
        elif schema == TDDCorrectionResponse:
            return TDDCorrectionResponse(
                explanation="Fixed imports and calculations",
                corrected_code="def run_computation(a, b):\n    return a + b\n"
            )
        elif schema == SkillSynthesisResponse:
            return SkillSynthesisResponse(
                rationale="Summarized python testing",
                markdown_instructions="# Pytest Tutorial\nStep 1: run pytest against your files.\n"
            )
        else:
            raise ValueError(f"Unknown schema: {schema}")


@pytest.mark.asyncio
async def test_propose_and_validate_mutation_integration(tmp_path: Path):
    db_path = tmp_path / "test_evolution.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        # Create target codebase file in tmp_path
        app_file = tmp_path / "calc.py"
        app_file.write_text("def run_computation(a, b):\n    return a - b  # bug\n", encoding="utf-8")

        # Create test file validating the calculation
        test_file = tmp_path / "test_calc.py"
        test_file.write_text(
            "from calc import run_computation\ndef test_calc():\n    assert run_computation(3, 4) == 7\n",
            encoding="utf-8"
        )

        llm = MockLLMCoordinatorClient()
        coordinator = SelfEvolutionCoordinator(db, llm, evolution_dir=tmp_path)

        success, var_id, test_msg = await coordinator.propose_and_validate_mutation(
            parent_id="v0_baseline",
            file_to_mutate=app_file,
            guidance="Correct calc subtraction to addition",
            test_file=test_file
        )

        assert success is True
        assert var_id.startswith("var_")
        assert "passed" in test_msg.lower()

        # Check UCB bandit feedback logged in manifest
        manifest = coordinator.self_mod.manifest
        assert manifest["total_runs"] == 1
        assert manifest["variants"][var_id]["average_score"] == 1.0

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_distill_trajectory_to_skill_integration(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test_evolution.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        # Insert a successful trajectory and steps into the DB
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("traj_success_123", "Write script and execute tests", 1, 3.2, 500, time.time())
        )
        
        await db.execute(
            """
            INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("traj_success_123", 1, "write_to_file", "calc.py", "saved calc.py", "decision", 100.0, 50)
        )
        await db.execute(
            """
            INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("traj_success_123", 2, "run_tests", "test_calc.py", "all tests passed!", "fact", 1200.0, 150)
        )

        llm = MockLLMCoordinatorClient()
        skills_dir = tmp_path / "skills"
        monkeypatch.setattr("silex.evolution.core.KINTHIC_SKILLS", skills_dir)
        monkeypatch.setattr("silex.evolution.admission_control.KINTHIC_SKILLS", skills_dir)
        coordinator = SelfEvolutionCoordinator(db, llm, evolution_dir=tmp_path)

        success, score = await coordinator.distill_trajectory_to_skill(
            trajectory_id="traj_success_123",
            category="testing",
            skill_name="pytest_skills",
            description="Guidelines on writing and executing pytest script test suites",
            threshold=0.70
        )

        assert success is True
        assert score >= 0.70

        nested_skill = skills_dir / "pytest_skills" / "SKILL.md"
        assert nested_skill.exists()
        assert "# Pytest Tutorial" in nested_skill.read_text(encoding="utf-8")

        # Verify database record in admitted_memories
        row = await db.fetch_one("SELECT * FROM admitted_memories WHERE skill_name = ?", ("pytest_skills",))
        assert row is not None
        assert row["category"] == "testing"
        assert row["origin_trajectory_id"] == "traj_success_123"

    finally:
        await db.close()
