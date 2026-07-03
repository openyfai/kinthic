"""
Self-Modification Engine for Kinthic (Phase 7.2).

Manages code mutations using UCB (Upper Confidence Bound) population search
and enforces safety safeguards (sacred file checks).
"""

from __future__ import annotations

import json
import math
import uuid
import time
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from silex.llm.base import SupportsLLM
from silex.utils.logger import setup_logger

log = setup_logger("silex.evolution.self_modification")

# ---------------------------------------------------------------------------
# Structured Output Schema for Code Mutation
# ---------------------------------------------------------------------------

class CodeMutationResponse(BaseModel):
    rationale: str = Field(..., description="Explanation of why this code mutation was proposed")
    mutated_code: str = Field(..., description="The entire contents of the mutated file (must be syntactically valid)")


# ---------------------------------------------------------------------------
# SelfModificationEngine
# ---------------------------------------------------------------------------

class SelfModificationEngine:
    """
    Manages population-based codebase self-modification.
    
    Enforces that mutated files avoid modifying sacred directories:
      - silex/memory/
      - silex/world/
      - silex/security/
      
    Uses UCB1 selection algorithm to balance exploration and exploitation of code variants.
    """

    SACRED_SUBSTRINGS = [
        "silex/memory", "silex/world", "silex/security",
        "silex/core", "silex/evolution", "silex/utils/config"
    ]

    def __init__(self, base_dir: Path | str | None = None, manifest_path: Path | str | None = None):
        if base_dir is None:
            self.base_dir = Path("~/.kinthic/evolution").expanduser()
        else:
            self.base_dir = Path(base_dir)

        if manifest_path is None:
            self.manifest_path = self.base_dir / "archive_manifest.json"
        else:
            self.manifest_path = Path(manifest_path)

        self.variants_dir = self.base_dir / "variants"
        self.variants_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self._load_or_init_manifest()

    def _load_or_init_manifest(self) -> dict[str, Any]:
        """Loads the manifest file or initializes it with a default structure."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to parse manifest {self.manifest_path}, initializing new one: {e}")
                
        # Initialize default manifest
        default_manifest = {
            "total_runs": 0,
            "variants": {
                "v0_baseline": {
                    "variant_id": "v0_baseline",
                    "path": "",  # Empty path indicates active production/baseline file
                    "parent_id": None,
                    "play_count": 0,
                    "score_sum": 0.0,
                    "average_score": 0.0,
                    "created_at": time.time()
                }
            }
        }
        self._save_manifest_data(default_manifest)
        return default_manifest

    def _save_manifest_data(self, data: dict[str, Any]) -> None:
        """Saves manifest payload to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_manifest(self) -> None:
        """Saves the current state of manifest to disk."""
        self._save_manifest_data(self.manifest)

    def is_path_safe(self, file_path: str | Path) -> bool:
        """
        Safety check: returns True if file path does not reference or modify
        any sacred files in silex/memory/, silex/world/, or silex/security/.
        """
        normalized = str(Path(file_path)).replace("\\", "/").lower()
        for sacred in self.SACRED_SUBSTRINGS:
            if sacred in normalized:
                log.warning(f"Safety violation: Path {file_path} contains sacred substring: {sacred}")
                return False
        return True

    def select_variant_ucb(self, exploration_constant: float = 1.414) -> dict[str, Any]:
        """
        Selects a code variant using the UCB1 multi-armed bandit algorithm.
        Balances exploitation (average score) and exploration (number of trials).
        """
        variants = self.manifest.get("variants", {})
        total_runs = self.manifest.get("total_runs", 0)

        if not variants:
            raise ValueError("No variants found in self-modification manifest.")

        best_variant = None
        best_ucb = -float("inf")

        for vid, v in variants.items():
            plays = v.get("play_count", 0)
            avg_score = v.get("average_score", 0.0)

            # If a variant has not been played yet, it gets infinite UCB to ensure exploration
            if plays == 0:
                ucb_val = float("inf")
            elif total_runs == 0:
                ucb_val = avg_score
            else:
                ucb_val = avg_score + exploration_constant * math.sqrt(math.log(total_runs) / plays)

            if ucb_val > best_ucb:
                best_ucb = ucb_val
                best_variant = v

        log.info(f"UCB Selection chose variant '{best_variant['variant_id']}' with UCB score {best_ucb}")
        return best_variant

    def register_variant(self, variant_id: str, path: str | Path, parent_id: str | None = None) -> None:
        """Registers a new code variant into the population manifest."""
        variants = self.manifest.setdefault("variants", {})
        if variant_id in variants:
            raise ValueError(f"Variant '{variant_id}' is already registered.")

        variants[variant_id] = {
            "variant_id": variant_id,
            "path": str(path),
            "parent_id": parent_id,
            "play_count": 0,
            "score_sum": 0.0,
            "average_score": 0.0,
            "created_at": time.time()
        }
        self.save_manifest()
        log.info(f"Registered new variant: {variant_id} at {path}")

    def record_feedback(self, variant_id: str, score: float) -> None:
        """Updates UCB selection metrics with evaluation run outcomes."""
        variants = self.manifest.setdefault("variants", {})
        if variant_id not in variants:
            log.warning(f"Unknown variant '{variant_id}' submitted feedback. Registering it dynamically.")
            self.register_variant(variant_id, "")

        v = variants[variant_id]
        v["play_count"] = v.get("play_count", 0) + 1
        v["score_sum"] = v.get("score_sum", 0.0) + score
        v["average_score"] = v["score_sum"] / v["play_count"]

        self.manifest["total_runs"] = self.manifest.get("total_runs", 0) + 1
        self.save_manifest()
        log.info(f"Recorded score {score} for variant '{variant_id}'. New play_count={v['play_count']}, avg={v['average_score']:.4f}")

    async def propose_mutation(
        self,
        parent_variant_id: str,
        file_to_mutate: str | Path,
        prompt_guidance: str,
        llm_client: SupportsLLM
    ) -> str:
        """
        Uses LLM to mutate an existing file, writes the mutation to a sandbox
        evolution variants folder, and registers it.
        """
        file_path = Path(file_to_mutate)
        
        # 1. Enforce safety checks
        if not self.is_path_safe(file_path):
            raise PermissionError(f"Access denied to modify sacred path: {file_path}")

        # 2. Find parent code
        variants = self.manifest.get("variants", {})
        if parent_variant_id not in variants:
            raise ValueError(f"Parent variant '{parent_variant_id}' not found.")
            
        parent_record = variants[parent_variant_id]
        parent_path_str = parent_record.get("path", "")
        
        if parent_path_str and Path(parent_path_str).exists():
            source_path = Path(parent_path_str)
        else:
            source_path = file_path

        if not source_path.exists():
            raise FileNotFoundError(f"Source file to mutate not found at: {source_path}")

        with open(source_path, "r", encoding="utf-8") as f:
            original_code = f.read()

        # 3. Request LLM mutation
        system_prompt = (
            "You are Kinthic's Metacognitive Codebase Mutation Engine (HyperAgent).\n"
            "Your task is to modify the provided code to satisfy the user's optimization request "
            "while maintaining syntax correctness, interfaces, and backward compatibility.\n"
            "You must return the COMPLETE modified source code file. Do not omit any sections."
        )

        user_input = json.dumps({
            "original_filename": file_path.name,
            "optimization_guidance": prompt_guidance,
            "original_code": original_code
        }, indent=2)

        log.info(f"Requesting mutation of '{file_path.name}' via LLM...")
        mutation_result: CodeMutationResponse = await llm_client.complete_json(
            schema=CodeMutationResponse,
            system_prompt=system_prompt,
            user_input=user_input,
            temperature=0.4
        )

        # 4. Save and register new variant
        new_variant_id = f"var_{uuid.uuid4().hex[:8]}"
        mutated_filename = f"{new_variant_id}_{file_path.name}"
        mutated_path = self.variants_dir / mutated_filename

        with open(mutated_path, "w", encoding="utf-8") as f:
            f.write(mutation_result.mutated_code)

        log.info(f"Saved mutated code to: {mutated_path}")
        
        self.register_variant(
            variant_id=new_variant_id,
            path=mutated_path,
            parent_id=parent_variant_id
        )

        return new_variant_id
