"""
System-level tools for advanced directory exploration and autonomous terminal execution.
These tools give ARIA deep OS-level insight.

Phase B Milestone 3: Terminal execution is now sandboxed using Docker for safety.
"""

from __future__ import annotations

from typing import Any
import os
import asyncio
import shlex
import copy
from pathlib import Path

try:
    import docker
except ImportError:
    docker = None

from silex.tools.base import BaseTool
from silex.utils.config import terminal_execution_enabled, WORKSPACE_DIR
from silex.utils.logger import setup_logger

log = setup_logger("silex.tools.system")
WORKSPACE_ROOT = WORKSPACE_DIR
BLOCKED_PATH_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".kinthic"}


def _resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
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
    """Executes bash commands autonomously inside a sandboxed environment."""

    name = "run_terminal_command"
    risk_level = "sandbox_write"
    requires_approval = True
    description = (
        "Executes a terminal command inside a safe, isolated Alpine Linux container if Docker is running, "
        "or falls back to a secure Python virtual environment (venv) sandbox with strict path/command validation "
        "rules if Docker is unavailable. "
        "Allows running tests, processing files safely, or installing packages."
    )
    schema = {
        "command": "string (The command to execute)"
    }

    def __init__(self):
        self._workspace_dir = WORKSPACE_ROOT
        self.client = None
        if docker:
            try:
                self.client = docker.from_env()
            except Exception as e:
                log.warning(f"Could not connect to Docker: {e}")



    def _validate_execution_bounds(self, argv: list[str]) -> None:
        """Physically block command arguments from referencing paths outside the workspace."""
        for token in argv:
            if ".." in token:
                raise PermissionError("Directory traversal ('..') is strictly prohibited.")
            
            # Look for path-like structures
            if "/" in token or "\\" in token or token.startswith("."):
                # Ignore common safe standard shells/files
                if token in ["/bin/sh", "/usr/bin/env", "/bin/bash", "/dev/null"]:
                    continue
                try:
                    p = Path(token)
                    if p.is_absolute():
                        p.relative_to(self._workspace_dir.resolve())
                    else:
                        resolved_p = (self._workspace_dir / p).resolve()
                        resolved_p.relative_to(self._workspace_dir.resolve())
                except ValueError:
                    raise PermissionError(
                        f"Access denied: command attempts to reference path outside workspace: '{token}'"
                    )

    def _check_safety(self, command: str, argv: list[str]) -> None:
        # Strict allowlist of commands
        allowed_commands = {"python", "python3", "pip", "git", "npm", "pytest", "ls", "cat", "echo", "mkdir", "touch", "grep", "node", "uv"}
        cmd_base = Path(argv[0]).name.lower()
        if cmd_base not in allowed_commands:
            raise PermissionError(f"Command '{cmd_base}' is not in the strict allowlist.")

        # Reject shell metacharacters — validation must match execution semantics
        shell_metachar = ("&&", "||", ";", "|", "&", "`", "$(", "${", "<(", ">(", "\n", "\r")
        for token in shell_metachar:
            if token in command:
                raise PermissionError(
                    f"Shell chaining/metacharacters are not permitted: found '{token}'"
                )

        # Intercept interpreters executing inline arguments in host fallback mode
        interpreter_binaries = {"python", "python3", "pythonw", "bash", "sh", "cmd", "powershell", "pwsh", "node", "perl", "ruby"}
        if cmd_base in interpreter_binaries:
            for arg in argv[1:]:
                arg_clean = arg.strip().lower()
                if arg_clean in ("-c", "-command", "/c", "-e", "--eval"):
                    raise PermissionError(
                        f"Access denied: inline script execution via {cmd_base} is prohibited in host fallback mode."
                    )

        # Check path bounds
        self._validate_execution_bounds(argv)

    async def _ensure_venv(self) -> Path:
        venv_dir = WORKSPACE_ROOT / ".venv"
        if not venv_dir.exists():
            log.info("Creating Python virtual environment sandbox...")
            import venv
            await asyncio.to_thread(venv.create, venv_dir, with_pip=True)
        return venv_dir

    async def execute(self, command: str) -> str:
        # Check the granular terminal-execution flag before doing anything.
        if not terminal_execution_enabled():
            return (
                "Error: Execution blocked. Autonomous terminal execution is currently "
                "disabled by the user for safety reasons. You must ask the user to "
                "set ARIA_ENABLE_TERMINAL_EXECUTION=true in the .env file to enable sandboxed execution."
            )

        # Tokenize arguments strictly
        argv = shlex.split(command)
        if not argv:
            return "Error: Command is empty."

        # Enforce strict safety validation (raises PermissionError if unsafe)
        try:
            self._check_safety(command, argv)
        except PermissionError as e:
            log.warning(f"Command rejected by sandbox safety controller: {e}")
            return f"Command execution rejected: {e}"


        if self.client:
            log.info(f"Executing Docker sandboxed command: {command}")
            try:
                # Ensure we have the alpine image
                try:
                    self.client.images.get("alpine:latest")
                except docker.errors.ImageNotFound:
                    log.info("Pulling alpine:latest image...")
                    self.client.images.pull("alpine:latest")

                self._workspace_dir.mkdir(parents=True, exist_ok=True)
                lab_dir = str(self._workspace_dir.resolve())

                container = self.client.containers.run(
                    image="alpine:latest",
                    command=argv,
                    volumes={
                        lab_dir: {"bind": "/workspace", "mode": "rw"},
                    },
                    working_dir="/workspace",
                    detach=True,
                    remove=True,
                    network_disabled=True,
                    mem_limit="256m",
                    pids_limit=128,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                )
                
                try:
                    result = await asyncio.to_thread(container.wait, timeout=60)
                except Exception:
                    container.kill()
                    return "Error: Sandboxed command timed out after 60 seconds."
                logs = (await asyncio.to_thread(container.logs)).decode("utf-8", errors="replace")
                exit_code = result.get("StatusCode", 0)
                
                return f"--- SANDBOX OUTPUT (Alpine Linux) ---\n{logs}\n--- END OUTPUT ---\nExit Code: {exit_code}"

            except Exception as e:
                log.error(f"Sandboxed execution failed: {e}")
                return f"Error executing sandboxed command: {str(e)}"
        
        else:
            log.info(f"Executing Local strict subprocess exec command: {command}")
            try:
                venv_dir = await self._ensure_venv()
                import shutil
                import sys
                
                # Prepend the venv bin/Scripts path to the PATH env var to enable venv path lookups
                env = copy.deepcopy(os.environ)
                if sys.platform == "win32":
                    venv_bin = venv_dir / "Scripts"
                else:
                    venv_bin = venv_dir / "bin"
                env["PATH"] = str(venv_bin) + os.path.pathsep + env.get("PATH", "")

                # Resolve binary from the path
                executable_path = shutil.which(argv[0], path=env["PATH"])
                if not executable_path:
                    executable_path = argv[0]

                proc = await asyncio.create_subprocess_exec(
                    executable_path,
                    *argv[1:],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self._workspace_dir),
                    env=env,
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                    exit_code = proc.returncode
                    logs = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return "Error: Local sandboxed command timed out after 60 seconds."

                return f"--- SANDBOX OUTPUT (Local Sandbox) ---\n{logs}\n--- END OUTPUT ---\nExit Code: {exit_code}"

            except Exception as e:
                log.error(f"Local sandbox execution failed: {e}")
                return f"Error executing local sandboxed command: {str(e)}"

    async def run_in_worker(self, command: str, lease: Any) -> str:
        """Run command in a worker container governed by a lease."""
        from agent.orchestrator import WorkerOrchestrator
        return await WorkerOrchestrator.instance().run_isolated(command, lease)
