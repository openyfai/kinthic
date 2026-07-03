"""
Runtime Capability Synthesis and Test-Driven Development (TDD) Loop (Phase 7.3).

Runs isolated tests with execution timeouts and performs iterative code refinement
using tracebacks and compiler/test feedback.
"""

from __future__ import annotations

import sys
import asyncio
import json
from pathlib import Path
from pydantic import BaseModel, Field

from silex.llm.base import SupportsLLM
from silex.utils.logger import setup_logger

log = setup_logger("silex.evolution.tdd_loops")

# ---------------------------------------------------------------------------
# Structured Output Schema for TDD Correction
# ---------------------------------------------------------------------------

class TDDCorrectionResponse(BaseModel):
    explanation: str = Field(..., description="Explanation of the code fixes applied to resolve the test failure")
    corrected_code: str = Field(..., description="The complete corrected source code file (must be syntactically valid)")


# ---------------------------------------------------------------------------
# RuntimeExtensionEngine
# ---------------------------------------------------------------------------

class RuntimeExtensionEngine:
    """
    Synthesizes and validates runtime code changes using Test-Driven Development (TDD).
    Spins up subprocesses to execute tests and feeds failures back to LLM for auto-correction.
    """

    def __init__(self, sandbox_dir: Path | str | None = None):
        if sandbox_dir is None:
            self.sandbox_dir = Path("~/.kronos/evolution/sandbox").expanduser()
        else:
            self.sandbox_dir = Path(sandbox_dir)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    async def run_tests(self, test_file: Path | str, timeout: float = 15.0) -> tuple[bool, str]:
        """
        Executes a test file inside an isolated python process.
        Enforces execution timeouts. Returns (success, output_string).
        """
        test_path = Path(test_file).resolve()
        if not test_path.exists():
            return False, f"Test file not found at: {test_path}"

        log.info(f"Running test file '{test_path.name}' (timeout={timeout}s)...")

        # Run pytest as a subprocess
        cmd = [sys.executable, "-m", "pytest", str(test_path), "-v"]
        
        try:
            # Run subprocess asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(test_path.parent)
            )
            
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                stdout = stdout_bytes.decode("utf-8", errors="ignore")
                stderr = stderr_bytes.decode("utf-8", errors="ignore")
                
                success = (process.returncode == 0)
                output = f"Stdout:\n{stdout}\nStderr:\n{stderr}"
                log.info(f"Tests finished. Success = {success}")
                return success, output
                
            except asyncio.TimeoutError:
                log.warning(f"Test suite execution timed out after {timeout} seconds. Killing process...")
                try:
                    process.kill()
                except OSError:
                    pass  # already dead
                return False, f"Test execution timed out after {timeout} seconds."
                
        except Exception as e:
            log.exception(f"Unexpected error running tests for {test_file}")
            return False, f"Exception occurred when launching tests: {e}"

    async def run_tdd_loop(
        self,
        file_to_mutate: Path | str,
        test_file: Path | str,
        prompt_guidance: str,
        llm_client: SupportsLLM,
        max_iterations: int = 3
    ) -> tuple[bool, str, str]:
        """
        Executes a closed-loop TDD flow:
          1. Run test suite.
          2. If pass -> return success.
          3. If fail -> extract traceback, prompt LLM to correct the code, write it back, repeat.
        """
        target_path = Path(file_to_mutate).resolve()
        test_path = Path(test_file).resolve()
        
        if not target_path.exists():
            raise FileNotFoundError(f"Target file to edit not found: {target_path}")

        current_code = target_path.read_text(encoding="utf-8")

        for iteration in range(1, max_iterations + 1):
            log.info(f"TDD Loop Iteration {iteration}/{max_iterations}")
            
            # 1. Run tests
            success, test_output = await self.run_tests(test_path)
            
            if success:
                log.info("TDD loop succeeded: All tests passed!")
                return True, "All tests passed successfully.", current_code

            log.warning(f"Tests failed on iteration {iteration}. Initiating self-correction...")
            
            # If this is the last iteration, we don't need to invoke LLM correction
            if iteration == max_iterations:
                break

            # 2. Query LLM to resolve failures
            system_prompt = (
                "You are Kronos's Automated Test-Driven Development Engine (TDD Loops).\n"
                "Review the original implementation guidance, the current source code, and the test failure output.\n"
                "Synthesize a corrected, syntactically valid implementation that resolves all failures.\n"
                "You must return the COMPLETE corrected source code. Do not omit any sections."
            )

            user_input = json.dumps({
                "filename": target_path.name,
                "guidance": prompt_guidance,
                "current_code": current_code,
                "test_failures": test_output[-2500:]  # Send tail of output to avoid context blowup
            }, indent=2)

            try:
                correction: TDDCorrectionResponse = await llm_client.complete_json(
                    schema=TDDCorrectionResponse,
                    system_prompt=system_prompt,
                    user_input=user_input,
                    temperature=0.2
                )
                
                # 3. Write corrections to target file
                current_code = correction.corrected_code
                target_path.write_text(current_code, encoding="utf-8")
                log.info(f"Applied TDD correction iteration {iteration}")
                
            except Exception as e:
                log.error(f"Failed to complete TDD correction round: {e}")
                return False, f"LLM self-correction error: {e}", current_code

        # Run one final time to return the exact final test result state
        success, test_output = await self.run_tests(test_path)
        if success:
            return True, "All tests passed successfully on final check.", current_code
            
        log.error("TDD loop failed: Max iterations reached without resolving test failures.")
        return False, test_output, current_code
