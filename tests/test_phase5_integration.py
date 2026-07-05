import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace
from silex.core.debate import DebateEngine
from silex.core.cognitive_loop import CognitiveLoop
from silex.models.schemas import DebateArgument, DebateResolution


@pytest.mark.asyncio
async def test_parallel_debate_execution():
    """Verify that DebateEngine runs agents A and B in parallel workers when parallel=True."""
    mock_llm = MagicMock()

    # Mock LLM completions for Agent A and Agent B arguments, and Judge synthesis
    async def capture_complete_json(schema, system_prompt, user_input, **kwargs):
        if schema == DebateArgument:
            return DebateArgument(
                agent_id="Agent A" if "Agent A" in system_prompt else "Agent B",
                claim="Test claim",
                reasoning="Test reasoning",
                evidence_or_logic="Test evidence",
            )
        elif schema == DebateResolution:
            return DebateResolution(
                summary="Transcendental truth",
                winner="Draw",
                strength_analysis={"Agent A": 5, "Agent B": 5},
                logical_fallacies={"Agent A": [], "Agent B": []},
                graph_updates=[],
                unresolved_contradiction_status={},
                strongest_points_a=["Point A"],
                strongest_points_b=["Point B"],
                synthesis="Good synthesis",
            )

    mock_llm.complete_json = capture_complete_json

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    # Mock WorkerOrchestrator
    mock_handle_a = MagicMock()
    mock_handle_a.workspace_dir = MagicMock()

    async def result_a():
        return "Agent A exit"

    mock_handle_a.result = result_a

    mock_handle_b = MagicMock()
    mock_handle_b.workspace_dir = MagicMock()

    async def result_b():
        return "Agent B exit"

    mock_handle_b.result = result_b

    call_count = 0

    async def fake_spawn_worker(task, tools, lease):
        nonlocal call_count
        call_count += 1
        return mock_handle_a if call_count == 1 else mock_handle_b

    with patch("agent.orchestrator.WorkerOrchestrator.instance") as mock_orch_inst:
        mock_orchestrator = MagicMock()
        mock_orchestrator.spawn_worker = MagicMock(side_effect=fake_spawn_worker)
        mock_orch_inst.return_value = mock_orchestrator

        engine = DebateEngine(llm_client=mock_llm, db=mock_db)
        resolution = await engine.run_debate(
            topic="Parallelism", rounds=1, parallel=True
        )

        assert resolution.summary == "Transcendental truth"
        assert call_count == 2


@pytest.mark.asyncio
async def test_chronos_background_tick_lifecycle():
    """Verify that CognitiveLoop.tick() correctly schedules, monitors, and completes background tasks."""
    loop = CognitiveLoop.__new__(CognitiveLoop)

    loop.goals = AsyncMock()
    mock_goal = SimpleNamespace(id="goal_123", description="Build something cool")
    loop.goals.get_active.return_value = [mock_goal]

    # db must be present from tick 1 onward (used for durable job recording)
    loop.db = AsyncMock()
    loop.db.execute = AsyncMock()

    loop.worker_orchestrator = MagicMock()
    mock_handle = MagicMock()
    mock_handle.status.return_value = "running"

    async def fake_spawn_job(job, lease):
        return mock_handle

    loop.worker_orchestrator.spawn_job = MagicMock(side_effect=fake_spawn_job)

    # Tick 1: Spawn worker
    await loop.tick()
    assert "goal_123" in loop._background_workers
    loop.worker_orchestrator.spawn_job.assert_called_once()

    # Tick 2: Goal is still running, shouldn't spawn a new one
    loop.worker_orchestrator.spawn_job.reset_mock()
    await loop.tick()
    loop.worker_orchestrator.spawn_job.assert_not_called()

    # Tick 3: Worker finished
    mock_handle.status.return_value = "done"

    async def fake_structured_result():
        from agent.jobs import WorkerJobResult

        return WorkerJobResult(
            job_id="job_test",
            worker_id="wid_test",
            success=True,
            exit_code=0,
            output="success final result",
        )

    mock_handle.structured_result = fake_structured_result

    loop.add_manual_memory = AsyncMock()

    await loop.tick()
    loop.add_manual_memory.assert_called_once()
    call_arg = loop.add_manual_memory.call_args[0][0]
    assert "Build something cool" in call_arg
    assert "success final result" in call_arg

    # Verify goal marked completed
    update_calls = [str(c) for c in loop.db.execute.call_args_list]
    assert any("completed" in c for c in update_calls)

    # Verify cleaned up
    assert "goal_123" not in loop._background_workers
