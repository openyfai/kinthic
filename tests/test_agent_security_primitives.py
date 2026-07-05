"""
Unit tests for agent security primitives (FilesystemPathGuardian and ActuationLease).
"""

import pytest
from pathlib import Path
from agent.security.path_guardian import FilesystemPathGuardian
from agent.security.lease import ActuationLease


def test_path_guardian_traversal_protection(tmp_path):
    """
    Verify that FilesystemPathGuardian canonicalizes paths and successfully blocks
    path traversal escapes, null-byte injections, and Git metadata access attempts.
    """
    sandbox_root = tmp_path / "workspace"
    sandbox_root.mkdir()
    guardian = FilesystemPathGuardian(sandbox_root)

    # Valid path should resolve successfully
    valid_file = sandbox_root / "src/index.js"
    canonical_valid = guardian.verify_and_canonicalize(valid_file)
    assert canonical_valid == valid_file.resolve(strict=False)

    # 1. Traverse upwards attempt
    with pytest.raises(PermissionError) as exc_info:
        guardian.verify_and_canonicalize(sandbox_root / "../outside_file.txt")
    assert "outside sandbox root" in str(exc_info.value)

    # 2. Absolute path traversal attempt
    with pytest.raises(PermissionError) as exc_info:
        # Resolving absolute path outside workspace
        outside_abs = Path("/absolute/outside/system_file").resolve()
        guardian.verify_and_canonicalize(outside_abs)
    assert "outside sandbox root" in str(exc_info.value)

    # 3. Null-byte injection attempt
    with pytest.raises(PermissionError) as exc_info:
        guardian.verify_and_canonicalize(sandbox_root / "safe_name.js\x00extra.py")
    assert "Null-byte injection" in str(exc_info.value)

    # 4. Accessing .git directory attempt
    with pytest.raises(PermissionError) as exc_info:
        guardian.verify_and_canonicalize(sandbox_root / ".git/config")
    assert "Git metadata directory" in str(exc_info.value)

    # 5. Writing to Git hooks directory attempt
    with pytest.raises(PermissionError) as exc_info:
        guardian.verify_and_canonicalize(sandbox_root / "src/.git/hooks/pre-commit")
    assert "Git metadata directory" in str(exc_info.value)


def test_actuation_lease_validation():
    """
    Verify that ActuationLease enforces TTL expiry, allowed tool boundaries,
    and cryptographic signature integrity checks.
    """
    task_id = "task_123"
    agent_id = "agent_456"

    # 1. Valid lease validation
    lease = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command", "file_write"],
    )
    assert lease.validate("run_terminal_command") is True
    assert lease.validate("file_write") is True

    # 2. Expired lease validation
    expired_lease = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=-10.0,  # Negative TTL to simulate instant expiration
        allowed_tools=["run_terminal_command"],
    )
    assert expired_lease.validate("run_terminal_command") is False

    # 3. Wrong tool permission validation
    assert lease.validate("read_file") is False

    # 4. Tampered parameter validation (violates signature)
    lease_tampered = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command"],
    )
    # Inject a tool maliciously in-memory
    lease_tampered.allowed_tools.append("arbitrary_execution")
    assert lease_tampered.validate("arbitrary_execution") is False

    # 5. Missing / altered signature validation
    lease_unsigned = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command"],
    )
    lease_unsigned.signature = None
    assert lease_unsigned.validate("run_terminal_command") is False

    lease_bad_signature = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command"],
    )
    lease_bad_signature.signature = "malicious_crafted_signature_here"
    assert lease_bad_signature.validate("run_terminal_command") is False

    # 6. Network default-deny validation
    lease_default_net = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command"],
    )
    assert lease_default_net.network_allowed is False

    lease_explicit_net = ActuationLease.issue(
        task_id=task_id,
        agent_id=agent_id,
        ttl_seconds=300.0,
        allowed_tools=["run_terminal_command"],
        network_allowed=True,
    )
    assert lease_explicit_net.network_allowed is True
    assert lease_explicit_net.validate("run_terminal_command") is True


@pytest.mark.asyncio
async def test_knowledge_graph_stats_keys(tmp_path):
    """Verify that KnowledgeGraph.stats() returns all keys required by TUI and dashboard."""
    from silex.storage.database import Database
    from silex.world.graph import KnowledgeGraph

    db_file = tmp_path / "silex.db"
    db = Database(str(db_file))
    await db.connect()

    # Create the tables
    await db.execute(
        "CREATE TABLE IF NOT EXISTS knowledge_nodes ("
        "id TEXT PRIMARY KEY, content TEXT, node_type TEXT, confidence REAL, source TEXT, "
        "created_at TEXT, last_validated TEXT, validation_count INTEGER, contradiction_count INTEGER, "
        "verification_status TEXT, metadata TEXT)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS causal_edges ("
        "id TEXT PRIMARY KEY, source_node TEXT, target_node TEXT, edge_type TEXT, "
        "strength REAL, evidence TEXT, created_at TEXT)"
    )

    kg = KnowledgeGraph(db)
    await kg.load()

    stats = kg.stats()
    assert "total_nodes" in stats
    assert "total_edges" in stats
    assert "node_count" in stats
    assert "edge_count" in stats
    assert "connected_components" in stats

    await db.close()
