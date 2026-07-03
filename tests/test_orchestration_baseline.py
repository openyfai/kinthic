"""
Baseline hardening tests for Kinthic orchestration (Phase A).
"""

import pytest
from unittest.mock import AsyncMock

from agent.orchestrator import WorkerOrchestrator
from agent.security.lease import ActuationLease


@pytest.mark.asyncio
async def test_spawn_worker_rejects_invalid_lease_tools(tmp_path):
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )
    lease = ActuationLease.issue("t1", "agent1", allowed_tools=["custom_tool"])

    with pytest.raises(PermissionError, match="lease"):
        await orchestrator.spawn_worker("echo hi", ["run_terminal_command"], lease)


@pytest.mark.asyncio
async def test_spawn_worker_rejects_expired_lease(tmp_path):
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )
    lease = ActuationLease.issue("t1", "agent1", ttl_seconds=-1, allowed_tools=["run_terminal_command"])

    with pytest.raises(PermissionError):
        await orchestrator.spawn_worker("echo hi", ["run_terminal_command"], lease)


@pytest.mark.asyncio
async def test_spawn_worker_teardown_after_success(tmp_path):
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )
    lease = ActuationLease.issue("t1", "agent1", allowed_tools=["run_terminal_command"])

    mock_kill = AsyncMock()
    mock_teardown = AsyncMock()

    async def mock_provision(lease=None):
        import uuid
        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.kill = mock_kill
        sandbox.execute.return_value = "--- SANDBOX OUTPUT ---\nok\nExit Code: 0"
        return sandbox

    orchestrator.provider = AsyncMock()
    orchestrator.provider.provision_sandbox = mock_provision
    orchestrator.provider.teardown_sandbox = mock_teardown

    handle = await orchestrator.spawn_worker("echo ok", ["run_terminal_command"], lease)
    await handle.result()

    mock_teardown.assert_called_once()
    assert handle.status() == "done"


@pytest.mark.asyncio
async def test_spawn_worker_fails_on_nonzero_exit(tmp_path):
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
    )
    lease = ActuationLease.issue("t1", "agent1", allowed_tools=["run_terminal_command"])

    async def mock_provision(lease=None):
        import uuid
        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.kill = AsyncMock()
        sandbox.execute.return_value = "--- SANDBOX OUTPUT ---\nfail\nExit Code: 1"
        return sandbox

    orchestrator.provider = AsyncMock()
    orchestrator.provider.provision_sandbox = mock_provision
    orchestrator.provider.teardown_sandbox = AsyncMock()

    handle = await orchestrator.spawn_worker("false", ["run_terminal_command"], lease)
    await handle.result()
    assert handle.status() == "failed"


@pytest.mark.asyncio
async def test_local_fallback_fail_closed_without_dev_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("KINTHIC_ALLOW_LOCAL_FALLBACK", raising=False)
    monkeypatch.delenv("KINTHIC_DEV_MODE", raising=False)

    from agent.compute.runtimes.warm_pool import DockerWarmPoolManager

    manager = DockerWarmPoolManager(
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
        pool_size=1,
    )
    manager.client = None

    with pytest.raises(RuntimeError, match="fail-closed"):
        await manager.provision_sandbox()


@pytest.mark.asyncio
async def test_local_fallback_allowed_with_dev_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("KINTHIC_ALLOW_LOCAL_FALLBACK", "1")

    from agent.compute.runtimes.warm_pool import DockerWarmPoolManager, LocalFallbackSandbox

    manager = DockerWarmPoolManager(
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project",
        pool_size=1,
    )
    manager.client = None

    sandbox = await manager.provision_sandbox()
    assert isinstance(sandbox, LocalFallbackSandbox)


def test_lease_validate_spawn_all_tools():
    lease = ActuationLease.issue("t", "a", allowed_tools=["a", "b"])
    assert lease.validate_spawn(["a", "b"]) is True
    assert lease.validate_spawn(["a", "c"]) is False


def test_lease_writable_path_scope():
    lease = ActuationLease.issue("t", "a", writable_paths=["/workspace/src"])
    assert lease.validate_writable_path("/workspace/src/foo.py") is True
    assert lease.validate_writable_path("/workspace/other/foo.py") is False
