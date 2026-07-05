"""
Unit tests for the Worker Orchestrator concurrency, lifecycle, and heartbeats.
"""

import time
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from agent.orchestrator import WorkerOrchestrator
from agent.security.lease import ActuationLease


@pytest.mark.asyncio
async def test_orchestrator_initialization(tmp_path):
    """Verify that WorkerOrchestrator initializes and registers correctly as a singleton."""
    orchestrator = WorkerOrchestrator(
        max_workers=2,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )
    assert WorkerOrchestrator.instance() == orchestrator
    assert orchestrator.max_workers == 2
    assert orchestrator.workspace_root == tmp_path / "workspace"


@pytest.mark.asyncio
async def test_orchestrator_concurrency_throttling(tmp_path):
    """Verify that WorkerOrchestrator throttles execution through its semaphore."""
    orchestrator = WorkerOrchestrator(
        max_workers=2,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )

    lease = ActuationLease.issue(
        "task_concurrency", "agent_concurrency", allowed_tools=["run_terminal_command"]
    )

    async def mock_provision(lease=None):
        import uuid

        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.execute.return_value = "--- SANDBOX OUTPUT ---\nSuccess\nExit Code: 0"
        return sandbox

    with patch(
        "agent.compute.runtimes.warm_pool.DockerWarmPoolManager.provision_sandbox",
        side_effect=mock_provision,
    ):
        # Spawn three parallel workers (max_workers=2)
        h1 = await orchestrator.spawn_worker("echo 1", ["run_terminal_command"], lease)
        h2 = await orchestrator.spawn_worker("echo 2", ["run_terminal_command"], lease)
        h3 = await orchestrator.spawn_worker("echo 3", ["run_terminal_command"], lease)

        # Wait for all to complete
        res = await asyncio.gather(h1.result(), h2.result(), h3.result())
        assert len(res) == 3
        assert "Success" in res[0]
        assert "Success" in res[1]
        assert "Success" in res[2]


@pytest.mark.asyncio
async def test_orchestrator_heartbeat_timeout(tmp_path):
    """Verify that WorkerOrchestrator terminates workers when their heartbeat halts."""
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )

    lease = ActuationLease.issue(
        "task_heartbeat", "agent_heartbeat", allowed_tools=["run_terminal_command"]
    )

    mock_kill = AsyncMock()

    async def mock_provision_heartbeat(lease=None):
        import uuid

        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.kill = mock_kill

        async def hang_execute(command, lease):
            heartbeat_file = wdir / "heartbeat.txt"
            heartbeat_file.write_text("1234567890", encoding="utf-8")
            import os

            os.utime(heartbeat_file, (time.time() - 60.0, time.time() - 60.0))
            await asyncio.sleep(0.5)
            return "Command completed"

        sandbox.execute.side_effect = hang_execute
        return sandbox

    original_sleep = asyncio.sleep

    async def custom_sleep(seconds):
        # If sleeping for heartbeat check intervals, make them instant to speed up test
        if seconds in (15, 5):
            await original_sleep(0.001)
        else:
            await original_sleep(seconds)

    with patch(
        "agent.compute.runtimes.warm_pool.DockerWarmPoolManager.provision_sandbox",
        side_effect=mock_provision_heartbeat,
    ):
        with patch("asyncio.sleep", custom_sleep):
            # Spawn a worker
            handle = await orchestrator.spawn_worker(
                "sleep 100", ["run_terminal_command"], lease
            )

            # Await the result. Heartbeat monitor will detect stale mtime and call kill()
            await handle.result()

            # Verify that kill was called and status is failed
            assert mock_kill.called
            assert handle.status() == "failed"


@pytest.mark.asyncio
async def test_orchestrator_spawn_cognitive_worker(tmp_path):
    """Verify that WorkerOrchestrator can spawn a cognitive worker job without AttributeError."""
    from agent.jobs import WorkerJob, WorkerClass
    from agent.security.lease import ActuationLease
    from agent.subagent import ChildAgentResult

    orchestrator = WorkerOrchestrator(
        max_workers=2,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )

    job = WorkerJob(
        objective="Analyze files",
        command="",
        worker_class=WorkerClass.COGNITIVE,
    )
    lease = ActuationLease.issue(job.job_id, job.agent_id)

    mock_result = ChildAgentResult(
        job_id=job.job_id,
        success=True,
        summary="Analysis complete. Found 2 issues.",
        turns_used=3,
        tokens_used=1200,
    )

    with patch(
        "agent.subagent.run_cognitive_subagent", return_value=mock_result
    ) as mock_run:
        handle = await orchestrator.spawn_job(job, lease)
        assert handle.task_id == job.job_id

        # Verify the handle registry works correctly now (no AttributeError)
        assert orchestrator._handles[job.job_id] == handle

        output = await handle.result()
        assert "Analysis complete" in output
        assert mock_run.called

        # Test structured result
        res = await handle.structured_result()
        assert res.success is True
        assert res.exit_code == 0
        assert res.output == "Analysis complete. Found 2 issues."
