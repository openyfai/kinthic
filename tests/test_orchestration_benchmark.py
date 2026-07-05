"""
Orchestration benchmark scenarios (Phase F).

Measures safety, recovery, delegation, and throughput characteristics
against explicit orchestration standards.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock

from agent.jobs import WorkerJob
from agent.orchestrator import WorkerOrchestrator
from agent.security.lease import ActuationLease


class OrchestrationBenchmark:
    """Internal scorecard for orchestration quality."""

    def __init__(self):
        self.scores: dict[str, float] = {}

    def record(self, category: str, passed: bool, weight: float = 1.0) -> None:
        self.scores[category] = self.scores.get(category, 0.0) + (
            weight if passed else 0.0
        )

    def total(self) -> float:
        return sum(self.scores.values())


def _mock_provider(orchestrator, tmp_path, exit_code: int = 0):
    async def mock_provision(lease=None):
        import uuid

        wid = f"worker_{uuid.uuid4().hex[:8]}"
        wdir = tmp_path / "workspace" / wid
        wdir.mkdir(parents=True, exist_ok=True)
        sandbox = AsyncMock()
        sandbox.worker_id = wid
        sandbox.workspace_dir = wdir
        sandbox.kill = AsyncMock()
        sandbox.execute.return_value = (
            f"--- SANDBOX OUTPUT ---\nout\nExit Code: {exit_code}"
        )
        return sandbox

    orchestrator.provider = AsyncMock()
    orchestrator.provider.provision_sandbox = mock_provision
    orchestrator.provider.teardown_sandbox = AsyncMock()


@pytest.mark.asyncio
async def test_benchmark_security_lease_bypass_denied(tmp_path):
    bench = OrchestrationBenchmark()
    orch = WorkerOrchestrator(
        max_workers=2, workspace_root=tmp_path / "ws", project_root=tmp_path / "proj"
    )
    lease = ActuationLease.issue("b1", "agent", allowed_tools=["safe_tool"])

    try:
        await orch.spawn_worker("echo x", ["run_terminal_command"], lease)
        bench.record("security_lease_bypass", False)
    except PermissionError:
        bench.record("security_lease_bypass", True)

    assert bench.scores["security_lease_bypass"] == 1.0


@pytest.mark.asyncio
async def test_benchmark_teardown_always_called(tmp_path):
    bench = OrchestrationBenchmark()
    orch = WorkerOrchestrator(
        max_workers=2, workspace_root=tmp_path / "ws", project_root=tmp_path / "proj"
    )
    _mock_provider(orch, tmp_path)
    lease = ActuationLease.issue("b2", "agent", allowed_tools=["run_terminal_command"])

    handle = await orch.spawn_worker("echo ok", ["run_terminal_command"], lease)
    await handle.result()
    bench.record("teardown_on_success", orch.provider.teardown_sandbox.called)
    assert bench.scores["teardown_on_success"] == 1.0


@pytest.mark.asyncio
async def test_benchmark_multi_agent_delegation_throughput(tmp_path):
    bench = OrchestrationBenchmark()
    orch = WorkerOrchestrator(
        max_workers=4, workspace_root=tmp_path / "ws", project_root=tmp_path / "proj"
    )
    _mock_provider(orch, tmp_path)

    jobs = [
        WorkerJob.from_command(f"echo task{i}", job_id=f"job_{i}") for i in range(6)
    ]
    start = time.monotonic()
    handles = []
    for job in jobs:
        lease = ActuationLease.issue(
            job.job_id, "bench", allowed_tools=job.allowed_tools
        )
        handles.append(await orch.spawn_job(job, lease))
    await asyncio.gather(*(h.result() for h in handles))
    elapsed = time.monotonic() - start

    bench.record("delegation_parallel", len(handles) == 6)
    bench.record("delegation_latency", elapsed < 5.0)
    assert bench.total() >= 2.0


@pytest.mark.asyncio
async def test_benchmark_nonzero_exit_recovery_semantics(tmp_path):
    bench = OrchestrationBenchmark()
    orch = WorkerOrchestrator(
        max_workers=1, workspace_root=tmp_path / "ws", project_root=tmp_path / "proj"
    )
    _mock_provider(orch, tmp_path, exit_code=2)
    lease = ActuationLease.issue("b3", "agent", allowed_tools=["run_terminal_command"])

    handle = await orch.spawn_worker("false", ["run_terminal_command"], lease)
    await handle.result()
    bench.record("nonzero_exit_failed", handle.status() == "failed")
    bench.record("teardown_on_failure", orch.provider.teardown_sandbox.called)
    assert bench.total() >= 2.0
