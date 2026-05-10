"""
System-level tools for advanced directory exploration and autonomous terminal execution.
These tools give ARIA deep OS-level insight.

Phase B Milestone 3: Terminal execution is now sandboxed using Docker for safety.
"""

from __future__ import annotations

import os
import logging
import asyncio
from pathlib import Path
from typing import Optional

try:
    import docker
except ImportError:
    docker = None

from aria.tools.base import BaseTool
from aria.utils.config import terminal_execution_enabled
from aria.utils.logger import setup_logger

log = setup_logger("aria.tools.system")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
BLOCKED_PATH_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


def _resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError("path is outside the project directory")
    if any(part in BLOCKED_PATH_PARTS for part in resolved.parts):
        raise ValueError("path includes a restricted directory")
    return resolved

class ListDirectoryTool(BaseTool):
    """Lists contents of a directory to map the codebase."""

    name = "list_directory"
    risk_level = "read_only"
    description = (
        "Lists the files and folders inside a specified directory path. "
        "Use this to explore the project structure."
    )
    schema = {
        "path": "string (The absolute or relative directory path to list)"
    }

    async def execute(self, path: str = ".") -> str:
        try:
            safe_path = _resolve_project_path(path)
        except ValueError as e:
            return f"Error: Access denied — {e}."

        if not safe_path.exists():
            return f"Error: Path '{path}' does not exist."
        if not safe_path.is_dir():
            return f"Error: Path '{path}' is not a directory."

        try:
            items = os.listdir(safe_path)
            directories = []
            files = []
            
            for item in items:
                full_path = safe_path / item
                if full_path.is_dir():
                    directories.append(f"📁 {item}/")
                else:
                    files.append(f"📄 {item}")
                    
            directories.sort()
            files.sort()
            
            output = f"Contents of {safe_path}:\n"
            output += "\n".join(directories + files)
            return output
            
        except Exception as e:
            return f"Error listing directory: {e}"


class RunTerminalCommandTool(BaseTool):
    """Executes bash commands autonomously inside a Docker sandbox."""

    name = "run_terminal_command"
    risk_level = "sandbox_write"
    requires_approval = True
    description = (
        "Executes a bash command inside a safe, isolated Alpine Linux container. "
        "The workspace is mapped to /workspace. "
        "Allows running tests, installing packages (inside sandbox), or processing files safely."
    )
    schema = {
        "command": "string (The bash command to execute)"
    }

    def __init__(self):
        self.client = None
        if docker:
            try:
                self.client = docker.from_env()
            except Exception as e:
                log.warning(f"Could not connect to Docker: {e}")

    async def execute(self, command: str) -> str:
        if not self.client:
            return "Error: Docker is not running or the Python SDK is not installed. Sandboxed execution is unavailable."

        # Check the granular terminal-execution flag before doing anything.
        if not terminal_execution_enabled():
            return (
                "Error: Execution blocked. Autonomous terminal execution is currently "
                "disabled by the user for safety reasons. You must ask the user to "
                "set ARIA_ENABLE_TERMINAL_EXECUTION=true in the .env file to enable sandboxed execution."
            )
            
        log.info(f"Executing sandboxed command: {command}")

        try:
            # Ensure we have the alpine image
            try:
                self.client.images.get("alpine:latest")
            except docker.errors.ImageNotFound:
                log.info("Pulling alpine:latest image...")
                self.client.images.pull("alpine:latest")

            # Execute in container with dual-volume mapping for maximum safety:
            # 1. Project Root -> /project (READ-ONLY)
            # 2. Project Workspace -> /workspace (READ-WRITE)
            cwd = str(PROJECT_ROOT)
            WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
            lab_dir = str(WORKSPACE_ROOT)
            
            container = self.client.containers.run(
                image="alpine:latest",
                command=["sh", "-c", command],
                volumes={
                    cwd: {"bind": "/project", "mode": "ro"},
                    lab_dir: {"bind": "/workspace", "mode": "rw"}
                },
                working_dir="/workspace",
                detach=True,
                remove=True,
                network_disabled=True,
                mem_limit="256m",
                pids_limit=128,
            )

            # Wait for container to finish and get logs
            # Since this is a simple run, we can just block for a bit or use wait()
            # For a truly async experience in a production app, we'd use a different pattern
            # but for a tool call, we wait.
            
            try:
                result = await asyncio.to_thread(container.wait, timeout=60)
            except Exception:
                container.kill()
                return "Error: Sandboxed command timed out after 60 seconds."
            logs = (await asyncio.to_thread(container.logs)).decode("utf-8", errors="replace")
            
            exit_code = result.get("StatusCode", 0)
            
            output = f"--- SANDBOX OUTPUT (Alpine Linux) ---\n{logs}\n--- END OUTPUT ---\nExit Code: {exit_code}"
            return output

        except Exception as e:
            log.error(f"Sandboxed execution failed: {e}")
            return f"Error executing sandboxed command: {str(e)}"
