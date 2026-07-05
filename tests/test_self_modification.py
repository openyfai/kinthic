"""
Unit tests for the Self Modification Engine (Phase 7.2).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from silex.evolution.self_modification import (
    SelfModificationEngine,
    CodeMutationResponse,
)


class MockLLMMutationClient:
    def __init__(self):
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
        self.calls.append((system_prompt, user_input))
        return CodeMutationResponse(
            rationale="Added caching logic to function.",
            mutated_code="def run():\n    print('cached run')\n",
        )


def test_manifest_load_and_save(tmp_path: Path):
    engine = SelfModificationEngine(base_dir=tmp_path)

    # Assert initialized with v0_baseline
    assert "v0_baseline" in engine.manifest["variants"]
    assert engine.manifest["total_runs"] == 0

    # Register a new variant
    variant_path = tmp_path / "var_1.py"
    variant_path.write_text("def run(): pass", encoding="utf-8")

    engine.register_variant("v1", variant_path, parent_id="v0_baseline")
    assert "v1" in engine.manifest["variants"]
    assert engine.manifest["variants"]["v1"]["path"] == str(variant_path)


def test_safety_check(tmp_path: Path):
    engine = SelfModificationEngine(base_dir=tmp_path)

    # Safe paths
    assert engine.is_path_safe("silex/adapters/optimizer.py") is True
    assert engine.is_path_safe("tests/test_optimizer.py") is True

    # Unsafe paths
    assert engine.is_path_safe("silex/memory/memory_store.py") is False
    assert engine.is_path_safe("silex/world/graph.py") is False
    assert engine.is_path_safe("silex/security/lease.py") is False
    assert engine.is_path_safe("E:/AGI/silex/memory/session.py") is False


def test_ucb_selection(tmp_path: Path):
    engine = SelfModificationEngine(base_dir=tmp_path)

    # Register multiple variants
    engine.register_variant("v1", tmp_path / "v1.py")
    engine.register_variant("v2", tmp_path / "v2.py")

    # With 0 plays, both v1 and v2 have infinite UCB. Let's see if one is picked
    selected = engine.select_variant_ucb()
    assert selected["variant_id"] in ("v1", "v2", "v0_baseline")

    # Play them and record feedback
    engine.record_feedback("v0_baseline", 0.5)
    engine.record_feedback("v1", 0.8)
    engine.record_feedback("v2", 0.9)

    # Now all have been played once. Total runs = 3
    # v2 has score 0.9, v1 has 0.8, baseline has 0.5
    # Let's verify that v2 (highest average score) gets selected when we request UCB with low exploration
    selected_exploit = engine.select_variant_ucb(exploration_constant=0.0)
    assert selected_exploit["variant_id"] == "v2"


@pytest.mark.asyncio
async def test_propose_mutation(tmp_path: Path):
    engine = SelfModificationEngine(base_dir=tmp_path)

    # Create original file to mutate
    original_file = tmp_path / "app.py"
    original_file.write_text("def run():\n    print('run')\n", encoding="utf-8")

    llm = MockLLMMutationClient()
    new_variant_id = await engine.propose_mutation(
        parent_variant_id="v0_baseline",
        file_to_mutate=original_file,
        prompt_guidance="Optimize performance",
        llm_client=llm,
    )

    assert new_variant_id.startswith("var_")

    # Verify the new variant was registered and written to files
    v_info = engine.manifest["variants"][new_variant_id]
    assert v_info["parent_id"] == "v0_baseline"

    written_path = Path(v_info["path"])
    assert written_path.exists()
    assert "cached run" in written_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_propose_mutation_sacred_path_denied(tmp_path: Path):
    engine = SelfModificationEngine(base_dir=tmp_path)
    llm = MockLLMMutationClient()

    with pytest.raises(PermissionError):
        await engine.propose_mutation(
            parent_variant_id="v0_baseline",
            file_to_mutate="silex/security/lease.py",
            prompt_guidance="Modify permissions",
            llm_client=llm,
        )
