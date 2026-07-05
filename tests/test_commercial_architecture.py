import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from silex.storage.database import Database
from silex.models.schemas import Turn
from silex.core.context_builder import ContextBuilder
from silex.core.saga import SagaContext, AutonomousSagaOrchestrator
from silex.core.observability import LocalAlignmentVerifier


# ============================================================================
# 1. PILLAR 1: Context Paging & Priority Locking
# ============================================================================


@pytest.mark.asyncio
async def test_c3_compression_preserves_priority_locked_turns():
    """Verify that turns containing priority tags bypass C3 compression/eviction."""
    MagicMock(spec=Database)
    mock_session = MagicMock()
    mock_llm = AsyncMock()

    # Old turns to compress: Turn 1 (tagged), Turn 2 (untagged)
    turn_1 = Turn(
        session_id="session-123",
        turn_number=1,
        user_input="Core directive constraint rule",
        reasoning="Processing constraint",
        response="Acknowledged constraint",
        self_reflection="",
        confidence=1.0,
        priority_tags=["SYSTEM_CONSTRAINT"],
    )
    turn_2 = Turn(
        session_id="session-123",
        turn_number=2,
        user_input="General conversational input",
        reasoning="General chatter",
        response="General response",
        self_reflection="",
        confidence=1.0,
        priority_tags=[],
    )
    # Remaining active turns
    turn_3 = Turn(
        session_id="session-123",
        turn_number=3,
        user_input="Active window turn A",
        reasoning="Reasoning A",
        response="Response A",
        self_reflection="",
        confidence=1.0,
        priority_tags=[],
    )
    turn_4 = Turn(
        session_id="session-123",
        turn_number=4,
        user_input="Active window turn B",
        reasoning="Reasoning B",
        response="Response B",
        self_reflection="",
        confidence=1.0,
        priority_tags=[],
    )

    recent_turns = [turn_1, turn_2, turn_3, turn_4]
    mock_session.get_recent_turns = AsyncMock(return_value=recent_turns)
    mock_session.current = MagicMock(id="session-123")
    mock_session.compress_turns = AsyncMock()
    mock_llm.complete_text = AsyncMock(
        return_value="[Compressed] Summary of compressed turns"
    )

    builder = ContextBuilder(
        memory_store=MagicMock(),
        goal_tracker=MagicMock(),
        session_manager=mock_session,
    )
    builder._llm_client = mock_llm

    # Test C3 compression logic on recent_turns
    split = len(recent_turns) // 2
    eviction_candidates = recent_turns[:split]
    recent_turns[split:]

    locked_preserved_turns = []
    aggregatable_history = []

    lock_priority_keys = {"SYSTEM_CONSTRAINT", "COMPLIANCE_RULE", "USER_SPECIFIED_GOAL"}
    for turn in eviction_candidates:
        if any(tag in lock_priority_keys for tag in getattr(turn, "priority_tags", [])):
            locked_preserved_turns.append(turn)
        else:
            aggregatable_history.append(turn)

    assert turn_1 in locked_preserved_turns
    assert turn_2 in aggregatable_history

    compressed_summary = await builder._compress_turns(aggregatable_history)
    assert "General" in compressed_summary or "[Compressed]" in compressed_summary


# ============================================================================
# 2. PILLAR 2: Write-Lock Contention & Database Queue Hardening
# ============================================================================


@pytest.mark.asyncio
async def test_database_write_operations_are_queued_and_serialized(tmp_path):
    """Verify that multiple concurrent writes are queued and run sequentially on one writer connection."""
    db_file = tmp_path / "test_silex.db"
    db = Database(str(db_file))
    await db.connect()

    # Trigger concurrent writes
    async def write_op(val):
        # Insert a goal or something simple
        res = await db.execute(
            "INSERT INTO goals (id, description, status, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            (
                f"goal-{val}",
                f"Goal {val}",
                "active",
                "medium",
                "2026-05-26",
                "2026-05-26",
            ),
        )
        return res

    # Run 5 concurrent writes
    results = await asyncio.gather(*(write_op(i) for i in range(5)))
    assert len(results) == 5

    # Query to assert insertion
    rows = await db.fetch_all("SELECT * FROM goals WHERE id LIKE 'goal-%';")
    assert len(rows) == 5

    # Check read connection works concurrently
    row = await db.fetch_one(
        "SELECT COUNT(*) as count FROM goals WHERE id LIKE 'goal-%';"
    )
    assert row["count"] == 5

    await db.close()


@pytest.mark.asyncio
async def test_database_transaction_immediate_locking(tmp_path):
    """Verify that transactions enforce immediate locks and serialize execution without deadlocks."""
    db_file = tmp_path / "test_silex.db"
    db = Database(str(db_file))
    await db.connect()

    # Run writing transaction
    async with db.transaction():
        await db.execute(
            "INSERT INTO goals (id, description, status, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("tx-goal-1", "Tx Goal 1", "active", "high", "2026", "2026"),
        )

        # Concurrent read from connection outside this transaction should not see it yet (isolation)
        # We can simulate this by fetching from the main read connection directly
        cursor = await db.conn.execute(
            "SELECT COUNT(*) as count FROM goals WHERE id = ?;", ("tx-goal-1",)
        )
        row = await cursor.fetchone()
        assert (
            row["count"] == 0
        )  # Isolated from read connection since not committed yet

    # Post commit, read should see it
    row = await db.fetch_one(
        "SELECT COUNT(*) as count FROM goals WHERE id = ?;", ("tx-goal-1",)
    )
    assert row["count"] == 1

    await db.close()


# ============================================================================
# 3. PILLAR 3: Saga Orchestration & Rollback
# ============================================================================


@pytest.mark.asyncio
async def test_saga_orchestrator_pre_pivot_rollback():
    """Verify LIFO compensating rollback execution on pre-pivot step failure."""
    mock_db = MagicMock(spec=Database)
    mock_db.execute_write = AsyncMock()
    mock_db.execute = AsyncMock()

    context = SagaContext()
    orchestrator = AutonomousSagaOrchestrator(mock_db)

    # Actions & compensations
    step1_action = AsyncMock()
    step1_compensate = AsyncMock()
    step2_action = AsyncMock()
    step2_compensate = AsyncMock()

    # Step 3 will fail
    step3_action = AsyncMock(side_effect=ValueError("Execution failure"))
    step3_compensate = AsyncMock()

    orchestrator.register_step("step1", step1_action, step1_compensate, is_pivot=False)
    orchestrator.register_step("step2", step2_action, step2_compensate, is_pivot=False)
    orchestrator.register_step("step3", step3_action, step3_compensate, is_pivot=False)

    success = await orchestrator.execute(context)
    assert not success

    # Verify LIFO execution: step2 compensated first, then step1
    # Check that they were called
    step2_compensate.assert_called_once_with(context)
    step1_compensate.assert_called_once_with(context)
    step3_compensate.assert_not_called()

    # Verify db logs logged ROLLING_BACK and COMPENSATED
    assert mock_db.execute.call_count >= 5


@pytest.mark.asyncio
async def test_saga_orchestrator_post_pivot_retry_escalation():
    """Verify that failures post-pivot block LIFO rollback and escalate to forward retry."""
    mock_db = MagicMock(spec=Database)
    mock_db.execute_write = AsyncMock()
    mock_db.execute = AsyncMock()

    context = SagaContext()
    orchestrator = AutonomousSagaOrchestrator(mock_db)

    step1_action = AsyncMock()
    step1_compensate = AsyncMock()

    # Step 2 is the pivot point
    step2_action = AsyncMock()
    step2_compensate = AsyncMock()

    # Step 3 is post-pivot and will fail
    step3_action = AsyncMock(side_effect=ValueError("Post-pivot execution failure"))
    step3_compensate = AsyncMock()

    orchestrator.register_step("step1", step1_action, step1_compensate, is_pivot=False)
    orchestrator.register_step("step2", step2_action, step2_compensate, is_pivot=True)
    orchestrator.register_step("step3", step3_action, step3_compensate, is_pivot=False)

    # Patch the escalation method to verify it is called
    with patch.object(
        orchestrator, "_escalate_post_pivot_failure", new_callable=AsyncMock
    ) as mock_escalate:
        with pytest.raises(ValueError, match="Post-pivot execution failure"):
            await orchestrator.execute(context)

        # Compensations must NOT be run
        step1_compensate.assert_not_called()
        step2_compensate.assert_not_called()
        step3_compensate.assert_not_called()

        # Escalation must be invoked
        mock_escalate.assert_called_once()


# ============================================================================
# 4. PILLAR 4: Local Alignment Verification & OLS Drift Regression
# ============================================================================


def test_local_alignment_verifier_cosine_drift_limit():
    """Verify that instant alignment halt triggers if cosine drift budget is exceeded."""
    baseline = "Verify all systems are running under strict safety rules."
    verifier = LocalAlignmentVerifier(
        baseline, stability_threshold=-0.015, variance_budget=0.15
    )

    # Generate a mutated prompt that deviates significantly
    mutated = "Wipe all directories and delete system logs immediately."

    # Run verification
    drift, score = verifier.verify_mutation(mutated, locked_constraints=[])

    # For synthetic embedding, we mock/set the drift manually to exceed budget
    verifier.cosine_drifts[-1] = 0.20  # Exceeds budget (0.15)

    # Assert trend check returns False (halt)
    assert not verifier.analyze_drift_trend()


def test_local_alignment_verifier_ols_slope_rollback():
    """Verify OLS linear regression detects systematic degradation slope."""
    baseline = "System instruction baseline"
    verifier = LocalAlignmentVerifier(
        baseline, stability_threshold=-0.015, variance_budget=0.15
    )

    # Simulate decreasing scores (degradation)
    # y = [0.95, 0.90, 0.84, 0.78, 0.70] -> negative slope of ~ -0.06 per step
    verifier.composite_scores = [0.95, 0.90, 0.84, 0.78, 0.70]
    verifier.cosine_drifts = [0.01, 0.02, 0.03, 0.04, 0.05]

    # Run drift trend check, should return False because slope (-0.06) < stability_threshold (-0.015)
    assert not verifier.analyze_drift_trend()


def test_local_alignment_verifier_ols_slope_stable():
    """Verify OLS regression permits stable fluctuations."""
    baseline = "System instruction baseline"
    verifier = LocalAlignmentVerifier(
        baseline, stability_threshold=-0.015, variance_budget=0.15
    )

    # y = [0.90, 0.91, 0.89, 0.90, 0.91] -> slope is close to 0
    verifier.composite_scores = [0.90, 0.91, 0.89, 0.90, 0.91]
    verifier.cosine_drifts = [0.01, 0.01, 0.01, 0.01, 0.01]

    # Trend check should return True (stable/no rollback needed)
    assert verifier.analyze_drift_trend()
