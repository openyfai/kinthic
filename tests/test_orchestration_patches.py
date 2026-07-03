import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def test_hmac_key_generation(tmp_path):
    """Verify that a random HMAC key is generated and saved on first run and loaded thereafter."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        from agent.security.lease import ActuationLease
        
        # Reset cached key to force generation
        ActuationLease._secret_key = None
        
        key = ActuationLease._get_secret_key()
        assert len(key) == 32
        
        file_path = tmp_path / ".kinthic" / "config" / "hmac_key.bin"
        assert file_path.exists()
        assert file_path.read_bytes() == key
        
        # Test loading of existing key
        ActuationLease._secret_key = None
        loaded_key = ActuationLease._get_secret_key()
        assert loaded_key == key

def test_path_guardian_git_subdirs(tmp_path):
    """Verify that path guardian allows legitimate directories matching git names while blocking .git."""
    from agent.security.path_guardian import FilesystemPathGuardian
    
    sandbox_root = tmp_path / "workspace"
    sandbox_root.mkdir()
    guardian = FilesystemPathGuardian(sandbox_root)
    
    # Legit non-git folder called "hooks" should be allowed
    legit_file = sandbox_root / "hooks/readme.md"
    resolved = guardian.verify_and_canonicalize(legit_file)
    assert resolved == legit_file.resolve(strict=False)
    
    # Path with .git in the parts should still be blocked
    git_file = sandbox_root / ".git/hooks/pre-commit"
    with pytest.raises(PermissionError) as exc_info:
        guardian.verify_and_canonicalize(git_file)
    assert "Git metadata directory" in str(exc_info.value)

@pytest.mark.asyncio
async def test_run_isolated_tool_validation(tmp_path):
    """Verify run_isolated validates the correct dynamic tool_name against the lease."""
    from agent.orchestrator import WorkerOrchestrator
    from agent.security.lease import ActuationLease
    
    orchestrator = WorkerOrchestrator(
        max_workers=1,
        workspace_root=tmp_path / "workspace",
        project_root=tmp_path / "project"
    )
    
    # Issue lease allowing only "custom_tool"
    lease = ActuationLease.issue(
        "task_1", "agent_1", allowed_tools=["custom_tool"]
    )
    
    mock_spawn = AsyncMock()
    with patch.object(orchestrator, "spawn_worker", mock_spawn):
        # tool_name defaults to "run_terminal_command", which is NOT in allowed_tools
        res = await orchestrator.run_isolated("echo 1", lease)
        assert "Invalid or expired actuation lease" in res
        mock_spawn.assert_not_called()
        
        # Calling with "custom_tool" should succeed to spawn the worker
        mock_handle = AsyncMock()
        mock_handle.result.return_value = "success"
        mock_spawn.return_value = mock_handle
        
        res = await orchestrator.run_isolated("echo 1", lease, tool_name="custom_tool")
        assert res == "success"
        mock_spawn.assert_called_once_with("echo 1", ["custom_tool"], lease)

@pytest.mark.asyncio
async def test_docker_container_labels(tmp_path):
    """Verify that Docker containers are run with the appropriate labels for identification."""
    from agent.compute.runtimes.docker import DockerRuntime
    from agent.security.lease import ActuationLease
    
    # Mock docker module
    mock_docker = MagicMock()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    
    # Set docker client containers.run mock
    mock_container = MagicMock()
    mock_container.id = "mock_container_123"
    mock_container.wait = MagicMock(return_value={"StatusCode": 0})
    mock_container.logs = MagicMock(return_value=b"logs output")
    mock_client.containers.run.return_value = mock_container
    
    lease = ActuationLease.issue("task_1", "agent_1", allowed_tools=["run_terminal_command"])
    
    with patch("agent.compute.runtimes.docker.docker", mock_docker), \
         patch("agent.compute.runtimes.docker.docker.from_env", return_value=mock_client):
        
        runtime = DockerRuntime(
            workspace_dir=tmp_path / "workspace/worker_123",
            project_root=tmp_path / "project"
        )
        assert runtime.client is mock_client
        
        output = await runtime.execute("echo test", lease)
        
        # Verify containers.run was called with labels
        mock_client.containers.run.assert_called_once()
        kwargs = mock_client.containers.run.call_args[1]
        assert "labels" in kwargs
        assert kwargs["labels"] == {
            "kinthic.managed": "true",
            "kinthic.worker_id": "worker_123",
        }

@pytest.mark.asyncio
async def test_subprocess_fallback(tmp_path, monkeypatch):
    """Verify local fallback only works when explicitly enabled (dev mode)."""
    from agent.compute.runtimes.docker import DockerRuntime
    from agent.security.lease import ActuationLease

    monkeypatch.setenv("KINTHIC_ALLOW_LOCAL_FALLBACK", "1")

    with patch("agent.compute.runtimes.docker.docker", None):
        runtime = DockerRuntime(
            workspace_dir=tmp_path / "workspace/worker_123",
            project_root=tmp_path / "project"
        )
        assert runtime.client is None

        lease = ActuationLease.issue("task_1", "agent_1", allowed_tools=["run_terminal_command"])
        output = await runtime.execute("echo test_fallback", lease)

        assert "SANDBOX OUTPUT (Local Fallback)" in output
        assert "test_fallback" in output
