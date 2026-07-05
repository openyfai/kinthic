"""
Unit tests for the Trajectory Optimizer (Phase 7.1).
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path

from silex.storage.database import Database
from silex.evolution.trajectory_optimizer import TrajectoryOptimizer
from silex.evolution.trajectory_optimizer import (
    TrajectoryRevisionResult,
    TrajectoryRefinementResult,
)


class MockLLMClient:
    def __init__(self):
        self.provider_name = "mock"
        self.default_model = "mock-model"
        self.calls = []

    def connect(self):
        pass

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
        self.calls.append((system_prompt, user_input, schema))
        if schema == TrajectoryRevisionResult:
            return TrajectoryRevisionResult(
                critique="The agent encountered a dead end on step 2.",
                step_revisions=[
                    {
                        "step_order": 2,
                        "revised_category": "dead_end",
                        "reasoning": "Step 2 failed because the target file did not exist.",
                    }
                ],
            )
        elif schema == TrajectoryRefinementResult:
            return TrajectoryRefinementResult(
                rationale="Compressed verbose output for step 2",
                step_refinements=[
                    {
                        "step_order": 2,
                        "compressed_output": "Compressed payload success",
                        "token_saved_estimate": 150,
                    }
                ],
            )
        else:
            raise ValueError(f"Unknown schema requested: {schema}")


@pytest.mark.asyncio
async def test_trajectory_revision(tmp_path: Path):
    db_path = tmp_path / "test_evolution.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        # Create mock failing trajectory
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("traj_fail_1", "Edit code and run test", 0, 12.5, 2000, time.time()),
        )

        await db.execute(
            """
            INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "traj_fail_1",
                1,
                "view_file",
                "path/to/file",
                "some contents",
                "fact",
                200.0,
                100,
            ),
        )
        await db.execute(
            """
            INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "traj_fail_1",
                2,
                "run_command",
                "pytest",
                "ModuleNotFoundError: No module named 'foo'",
                "hypothesis",
                1500.0,
                500,
            ),
        )

        llm = MockLLMClient()
        optimizer = TrajectoryOptimizer(db, llm)

        result = await optimizer.run_revision("traj_fail_1")

        # Verify LLM response was incorporated
        assert "dead end" in result["critique"]
        assert len(result["step_revisions"]) == 1
        assert result["step_revisions"][0]["step_order"] == 2
        assert result["step_revisions"][0]["revised_category"] == "dead_end"

        # Verify DB update happened
        updated_step = await db.fetch_one(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? AND step_order = ?",
            ("traj_fail_1", 2),
        )
        assert updated_step is not None
        assert updated_step["epistemic_category"] == "dead_end"

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_trajectory_recombination(tmp_path: Path):
    db_path = tmp_path / "test_evolution.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        # Create two successful trajectories with a crossover point (view_file)
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("t1", "Fix bug in parser", 1, 5.0, 1000, time.time()),
        )
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("t2", "Refactor parsing unit", 1, 6.0, 1200, time.time()),
        )

        # Steps for T1
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t1", 1, "initialize", "{}", "init ok", "fact", 100.0, 50),
        )
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t1",
                2,
                "view_file",
                "parser.py",
                "def parse(): pass",
                "fact",
                200.0,
                150,
            ),
        )
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t1",
                3,
                "run_command",
                "pytest parser.py",
                "parser passed",
                "decision",
                1000.0,
                300,
            ),
        )

        # Steps for T2
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t2", 1, "initialize", "{}", "init ok", "fact", 100.0, 50),
        )
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t2",
                2,
                "view_file",
                "parser.py",
                "def parse(): pass",
                "fact",
                200.0,
                150,
            ),
        )
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t2",
                3,
                "replace_file_content",
                "parser.py",
                "modified ok",
                "decision",
                500.0,
                200,
            ),
        )
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t2", 4, "run_command", "pytest tests/", "all green", "fact", 1500.0, 400),
        )

        llm = MockLLMClient()
        optimizer = TrajectoryOptimizer(db, llm)

        recomb_id = await optimizer.run_recombination("t1", "t2")
        assert recomb_id is not None
        assert recomb_id.startswith("recomb_")

        # Retrieve new trajectory
        new_traj = await db.fetch_one(
            "SELECT * FROM trajectories WHERE trajectory_id = ?", (recomb_id,)
        )
        assert new_traj is not None
        assert new_traj["is_success"] == 1

        # Retrieve combined steps
        # Splicing at view_file (T1 index 1, T2 index 1)
        # Expected combined steps:
        # Step 1: T1 Step 1 (initialize)
        # Step 2: T1 Step 2 (view_file)
        # Step 3: T2 Step 3 (replace_file_content)
        # Step 4: T2 Step 4 (run_command)
        c_steps = await db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (recomb_id,),
        )
        assert len(c_steps) == 4
        assert c_steps[0]["action_name"] == "initialize"
        assert c_steps[1]["action_name"] == "view_file"
        assert c_steps[2]["action_name"] == "replace_file_content"
        assert c_steps[3]["action_name"] == "run_command"

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_trajectory_refinement(tmp_path: Path):
    db_path = tmp_path / "test_evolution.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        # Create trajectory for refinement with:
        # 1. Consecutive duplicate tool calls (run_command pytest)
        # 2. Large output (> 500 chars) for step 2
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("t_refine", "Refinement demo", 1, 5.0, 1000, time.time()),
        )

        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t_refine", 1, "initialize", "{}", "init ok", "fact", 100.0, 50),
        )
        # Verbose output (>500 chars)
        verbose_out = "A" * 600
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t_refine",
                2,
                "run_command",
                "pytest",
                verbose_out,
                "decision",
                1500.0,
                800,
            ),
        )
        # Duplicate consecutive step
        await db.execute(
            "INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "t_refine",
                3,
                "run_command",
                "pytest",
                verbose_out,
                "decision",
                1500.0,
                800,
            ),
        )

        llm = MockLLMClient()
        optimizer = TrajectoryOptimizer(db, llm)

        refined_id = await optimizer.run_refinement("t_refine")
        assert refined_id == "t_refine"

        # Check DB steps
        r_steps = await db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            ("t_refine",),
        )
        # The duplicate step 3 should have been pruned, leaving exactly 2 steps.
        assert len(r_steps) == 2

        # Verify step 1 remains initialize
        assert r_steps[0]["action_name"] == "initialize"

        # Verify step 2 output was compressed by MockLLMClient (from "A"*600 to "Compressed payload success")
        assert r_steps[1]["action_name"] == "run_command"
        assert r_steps[1]["execution_output"] == "Compressed payload success"
        # Token usage was 800, saved 150 -> should be 650
        assert r_steps[1]["token_usage"] == 650

    finally:
        await db.close()
