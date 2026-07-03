"""
Tests for structured worker job model (Phase B).
"""

import pytest
from unittest.mock import AsyncMock

from agent.jobs import WorkerJob, WorkerJobResult
from agent.orchestrator import WorkerOrchestrator
from agent.security.lease import ActuationLease


def test_worker_job_roundtrip():
    job = WorkerJob.from_command("echo hello", objective="Say hello")
    data = job.to_dict()
    restored = WorkerJob.from_dict(data)
    assert restored.command == "echo hello"
    assert restored.objective == "Say hello"


@pytest.mark.asyncio
async def test_spawn_job_returns_structured_result(tmp_path):
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )

    async def mock_provision(lease=None):
        import uuid
        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.kill = AsyncMock()
        sandbox.execute.return_value = "--- SANDBOX OUTPUT ---\nok\nExit Code: 0"
        return sandbox

    orchestrator.provider = AsyncMock()
    orchestrator.provider.provision_sandbox = mock_provision
    orchestrator.provider.teardown_sandbox = AsyncMock()

    job = WorkerJob.from_command("echo structured", objective="Test structured output")
    lease = ActuationLease.issue(job.job_id, job.agent_id, allowed_tools=job.allowed_tools)

    handle = await orchestrator.spawn_job(job, lease)
    result = await handle.structured_result()

    assert isinstance(result, WorkerJobResult)
    assert result.success is True
    assert result.job_id == job.job_id
