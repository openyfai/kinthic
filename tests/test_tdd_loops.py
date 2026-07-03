"""
Unit and integration tests for the TDD Loops engine (Phase 7.3).
"""

from __future__ import annotations

import pytest
from pathlib import Path
from silex.evolution.tdd_loops import RuntimeExtensionEngine, TDDCorrectionResponse


class MockLLMTDDRedirect:
    def __init__(self, corrected_code: str):
        self.corrected_code = corrected_code
        self.calls = []

    async def complete_json(
        self,
        *,
        schema,
        system_prompt,
        user_input,
        images=None,
        model_override=None,
        temperature=0.7,
        request_kind="chat",
    ):
        self.calls.append(user_input)
        return TDDCorrectionResponse(
            explanation="Fixed the return value to match expectation.",
            corrected_code=self.corrected_code
        )


@pytest.mark.asyncio
async def test_run_tests_success_and_fail(tmp_path: Path):
    engine = RuntimeExtensionEngine(sandbox_dir=tmp_path)
    
    # 1. Create a passing test file
    pass_test = tmp_path / "test_passing.py"
    pass_test.write_text(
        "def test_success():\n    assert 1 + 1 == 2\n",
        encoding="utf-8"
    )
    
    success, output = await engine.run_tests(pass_test, timeout=5.0)
    assert success is True
    assert "test_passing.py" in output or "success" in output.lower()

    # 2. Create a failing test file
    fail_test = tmp_path / "test_failing.py"
    fail_test.write_text(
        "def test_failure():\n    assert 1 + 1 == 99\n",
        encoding="utf-8"
    )
    
    success, output = await engine.run_tests(fail_test, timeout=5.0)
    assert success is False
    assert "AssertionError" in output


@pytest.mark.asyncio
async def test_run_tests_timeout(tmp_path: Path):
    engine = RuntimeExtensionEngine(sandbox_dir=tmp_path)
    
    # Create a test file that sleeps forever (longer than timeout)
    hanging_test = tmp_path / "test_hang.py"
    hanging_test.write_text(
        "import time\ndef test_hanging():\n    time.sleep(10)\n",
        encoding="utf-8"
    )
    
    # Run with a very short timeout (0.5 seconds)
    success, output = await engine.run_tests(hanging_test, timeout=0.5)
    assert success is False
    assert "timed out" in output.lower() or "timeout" in output.lower()


@pytest.mark.asyncio
async def test_tdd_loop_self_corrects(tmp_path: Path):
    engine = RuntimeExtensionEngine(sandbox_dir=tmp_path)
    
    # Create a code file with a bug
    app_file = tmp_path / "math_app.py"
    app_file.write_text(
        "def add_numbers(a, b):\n    return a - b  # Bug!\n",
        encoding="utf-8"
    )
    
    # Create a test file validating add_numbers
    test_file = tmp_path / "test_math_app.py"
    test_file.write_text(
        "from math_app import add_numbers\ndef test_add():\n    assert add_numbers(2, 3) == 5\n",
        encoding="utf-8"
    )
    
    # The corrected code that the LLM will supply
    fixed_code = "def add_numbers(a, b):\n    return a + b\n"
    llm = MockLLMTDDRedirect(corrected_code=fixed_code)
    
    # Execute TDD loop
    success, log_msg, final_code = await engine.run_tdd_loop(
        file_to_mutate=app_file,
        test_file=test_file,
        prompt_guidance="Fix add_numbers to perform addition",
        llm_client=llm,
        max_iterations=3
    )
    
    assert success is True
    assert "passed" in log_msg.lower()
    assert "a + b" in final_code
    assert app_file.read_text(encoding="utf-8") == fixed_code
