"""
Tests for git worktree workspace isolation (Phase C).
"""

import subprocess

import pytest

from agent.collaboration.worktree import WorktreeManager


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    return repo


def test_worktree_create_and_remove(git_repo, tmp_path):
    manager = WorktreeManager(git_repo, worktrees_root=tmp_path / "worktrees")
    path = manager.create_worktree("agent_test")
    assert path.exists()

    manager.remove_worktree(path)
    # worktree directory should be gone or empty after remove
    assert not path.exists() or not any(path.iterdir())


def test_worktree_fallback_non_git(tmp_path):
    not_git = tmp_path / "plain"
    not_git.mkdir()
    manager = WorktreeManager(not_git, worktrees_root=tmp_path / "worktrees")
    path = manager.create_worktree("agent_plain")
    assert path.exists()
