"""
silex/autonomy/export.py — Trajectory export pipeline for RL / fine-tuning.

Exports the `trajectories` + `trajectory_steps` tables into formats compatible
with modern RL / SFT training frameworks:

  SFT (Supervised Fine-Tuning)
    One record per trajectory.  The full tool-call sequence is rolled into
    the ``completion`` field.  Reward is attached as metadata.

    Compatible with: Unsloth, Axolotl, LLaMA-Factory, TRL SFTTrainer.

  GRPO (Group Relative Policy Optimisation)
    One record per trajectory, with a scalar reward.  The ``responses``
    list mirrors Atropos / TRL GRPOTrainer expectations.

    Compatible with: TRL GRPOTrainer, Atropos, OpenRLHF.

  CSV
    Flat tabular dump of all trajectories with reward columns.  Useful for
    offline analysis in notebooks.

Usage (Python)::

    from silex.autonomy.export import export_trajectories
    await export_trajectories(db, format="grpo", output_path=Path("data/train.jsonl"))

Usage (CLI)::

    kinthic export-trajectories --format grpo --output ~/train.jsonl
    kinthic export-trajectories --format sft --success-only --since 2026-01-01
"""
from __future__ import annotations

import csv
import datetime
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("silex.autonomy.export")

# ---------------------------------------------------------------------------
# Reward configuration
# ---------------------------------------------------------------------------

# How much each epistemic step category contributes to step-level reward (0–1)
STEP_CATEGORY_SCORE: dict[str, float] = {
    "decision": 1.0,
    "fact":     0.9,
    "hypothesis": 0.6,
    "dead_end": 0.0,
}

# BenchmarkScenario.level → normalised reward bonus (0–1)
# ScoreLevel: ZERO=0, POOR=1, PARTIAL=2, ADEQUATE=3, GOOD=4, EXCELLENT=5
SCENARIO_LEVEL_BONUS: dict[int, float] = {
    0: 0.0,
    1: 0.1,
    2: 0.3,
    3: 0.5,
    4: 0.7,
    5: 1.0,
}


@dataclass
class ExportConfig:
    """Controls what is exported and how rewards are computed."""

    format: Literal["sft", "grpo", "csv"] = "grpo"
    output_path: Path | None = None
    success_only: bool = False
    min_steps: int = 1
    max_steps: int = 256
    since_ts: float | None = None          # unix timestamp lower bound
    until_ts: float | None = None          # unix timestamp upper bound
    include_failed_steps: bool = True      # include dead_end steps in rollout text
    max_trajectories: int = 10_000
    benchmark_weight: float = 0.2          # how much benchmark bonus counts in reward
    step_quality_weight: float = 0.3       # how much step-category quality counts
    outcome_weight: float = 0.5            # how much is_success counts


@dataclass
class ExportRecord:
    """A single training record before serialisation."""

    trajectory_id: str
    task_description: str
    prompt: str
    completion: str                        # rollout text of steps
    reward: float                          # 0.0–1.0 scalar
    is_success: bool
    total_tokens: int
    step_count: int
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sft(self) -> dict[str, Any]:
        """Unsloth / Axolotl / TRL SFTTrainer format."""
        return {
            "prompt":     self.prompt,
            "completion": self.completion,
            "reward":     round(self.reward, 4),
            "metadata": {
                "trajectory_id": self.trajectory_id,
                "is_success":    self.is_success,
                "total_tokens":  self.total_tokens,
                "step_count":    self.step_count,
                "timestamp":     datetime.datetime.utcfromtimestamp(self.timestamp).isoformat(),
                **self.metadata,
            },
        }

    def to_grpo(self) -> dict[str, Any]:
        """
        TRL GRPOTrainer / Atropos format.

        ``prompt``    — the user instruction
        ``responses`` — list of rollout strings (one trajectory = one response)
        ``rewards``   — parallel list of scalar rewards
        ``advantages``— (reward − mean) / std; pre-computed where possible
        """
        return {
            "prompt":     self.prompt,
            "responses":  [self.completion],
            "rewards":    [round(self.reward, 4)],
            # advantage is filled in post-processing after batch mean/std are known
            "advantages": [None],
            "metadata": {
                "trajectory_id": self.trajectory_id,
                "is_success":    self.is_success,
                "total_tokens":  self.total_tokens,
                "step_count":    self.step_count,
                "timestamp":     datetime.datetime.utcfromtimestamp(self.timestamp).isoformat(),
                **self.metadata,
            },
        }

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "trajectory_id":   self.trajectory_id,
            "task_description": self.task_description[:120],
            "is_success":      int(self.is_success),
            "reward":          round(self.reward, 4),
            "total_tokens":    self.total_tokens,
            "step_count":      self.step_count,
            "timestamp":       datetime.datetime.utcfromtimestamp(self.timestamp).isoformat(),
            **{k: str(v)[:80] for k, v in self.metadata.items()},
        }


# ---------------------------------------------------------------------------
# Reward computation
# ---------------------------------------------------------------------------

def _compute_reward(
    is_success: bool,
    steps: list[dict[str, Any]],
    cfg: ExportConfig,
    benchmark_bonus: float = 0.0,
) -> float:
    """
    Compute a scalar reward in [0, 1] for one trajectory.

    Components
    ----------
    outcome      : is_success flag (weighted by cfg.outcome_weight)
    step_quality : mean epistemic category score of all steps
                   (weighted by cfg.step_quality_weight)
    benchmark    : bonus from BenchmarkScenario match
                   (weighted by cfg.benchmark_weight)
    """
    outcome_score = 1.0 if is_success else 0.0

    if steps:
        step_scores = [
            STEP_CATEGORY_SCORE.get(s.get("epistemic_category", "decision"), 0.5)
            for s in steps
        ]
        step_quality = sum(step_scores) / len(step_scores)
    else:
        step_quality = 0.0

    # Normalise weights so they always sum to 1 even if benchmark_bonus is absent
    total_w = cfg.outcome_weight + cfg.step_quality_weight + cfg.benchmark_weight
    reward = (
        cfg.outcome_weight    / total_w * outcome_score
        + cfg.step_quality_weight / total_w * step_quality
        + cfg.benchmark_weight    / total_w * benchmark_bonus
    )
    return min(max(round(reward, 4), 0.0), 1.0)


def _build_rollout_text(
    steps: list[dict[str, Any]],
    include_failed: bool,
) -> str:
    """
    Render trajectory steps into a readable rollout string for the completion field.

    Format (one line per step)::

        [step 1 | decision] tool_name({"arg": "val"}) → output…
    """
    parts: list[str] = []
    for s in steps:
        cat = s.get("epistemic_category", "decision")
        if not include_failed and cat == "dead_end":
            continue
        action   = s.get("action_name", "?")
        inp      = s.get("tool_input",  "")[:200]
        out      = s.get("execution_output", "")[:300]
        order    = s.get("step_order", "?")
        parts.append(f"[step {order} | {cat}] {action}({inp}) → {out}")
    return "\n".join(parts) if parts else "(no steps)"


# ---------------------------------------------------------------------------
# BenchmarkScenario index for reward bonus
# ---------------------------------------------------------------------------

def _build_scenario_index() -> dict[str, float]:
    """
    Return a dict mapping lower-case keywords from scenario names/descriptions
    to their normalised expected score.
    """
    try:
        from agent.benchmarks.scenarios import ORCHESTRATION_BENCHMARKS, SCENARIO_LEVEL_BONUS as _lvl  # type: ignore[attr-defined]
    except ImportError:
        try:
            from agent.benchmarks.scenarios import ORCHESTRATION_BENCHMARKS  # type: ignore[import]
        except ImportError:
            return {}

    index: dict[str, float] = {}
    for sc in ORCHESTRATION_BENCHMARKS:
        bonus = SCENARIO_LEVEL_BONUS.get(sc.level, 0.5)
        for word in (sc.name + " " + sc.description).lower().split():
            if len(word) >= 5:
                index[word] = max(index.get(word, 0.0), bonus)
    return index


def _get_benchmark_bonus(task_description: str, index: dict[str, float]) -> float:
    """Return the highest matching benchmark bonus for this task description."""
    if not index:
        return 0.0
    words = task_description.lower().split()
    hits = [index[w] for w in words if w in index]
    return max(hits) if hits else 0.0


# ---------------------------------------------------------------------------
# Reward model — importable by TrajectoryOptimizer and other callers
# ---------------------------------------------------------------------------

class RewardComputer:
    """
    Computes scalar rewards for trajectories.

    Can be used independently by the TrajectoryOptimizer, benchmark harness,
    or any caller that wants a consistent reward signal without running a full
    export.

    Reward formula
    --------------
    reward = outcome_w   × outcome_score      (0 or 1, from is_success)
           + step_w      × step_quality       (mean epistemic category score)
           + bench_w     × benchmark_bonus    (BenchmarkScenario match)

    All three components are normalised to [0, 1].
    """

    def __init__(self, cfg: ExportConfig | None = None) -> None:
        self.cfg = cfg or ExportConfig()
        self._bonus_index: dict[str, float] | None = None

    def _get_bonus_index(self) -> dict[str, float]:
        if self._bonus_index is None:
            self._bonus_index = _build_scenario_index()
        return self._bonus_index

    def compute(
        self,
        *,
        is_success: bool,
        steps: list[dict[str, Any]],
        task_description: str = "",
        benchmark_score_0_to_1: float | None = None,
    ) -> dict[str, Any]:
        """
        Compute reward and return a breakdown dict.

        Returns
        -------
        {
          "reward": float,
          "outcome": float,
          "step_quality": float,
          "benchmark_bonus": float,
          "step_scores": list[float],
        }
        """
        outcome = 1.0 if is_success else 0.0

        step_scores = [
            STEP_CATEGORY_SCORE.get(s.get("epistemic_category", "decision"), 0.5)
            for s in steps
        ]
        step_quality = sum(step_scores) / len(step_scores) if step_scores else 0.0

        if benchmark_score_0_to_1 is not None:
            bonus = float(benchmark_score_0_to_1)
        else:
            bonus = _get_benchmark_bonus(task_description, self._get_bonus_index())

        reward = _compute_reward(is_success, steps, self.cfg, bonus)

        return {
            "reward":          reward,
            "outcome":         outcome,
            "step_quality":    round(step_quality, 4),
            "benchmark_bonus": round(bonus, 4),
            "step_scores":     [round(s, 4) for s in step_scores],
        }


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

async def export_trajectories(
    db: Any,
    cfg: ExportConfig | None = None,
    *,
    format: Literal["sft", "grpo", "csv"] = "grpo",
    output_path: "Path | str | None" = None,
    success_only: bool = False,
    since: "str | None" = None,
    until: "str | None" = None,
    max_trajectories: int = 10_000,
) -> tuple[list[ExportRecord], Path | None]:
    """
    Export trajectories from the database as training data.

    Parameters
    ----------
    db : Database
        Async database instance.
    cfg : ExportConfig | None
        Full configuration object; keyword args below are used when cfg is None.
    format : 'sft' | 'grpo' | 'csv'
    output_path : path to write output (auto-named if None)
    success_only : only include successful trajectories
    since : ISO date string (YYYY-MM-DD) lower bound
    until : ISO date string (YYYY-MM-DD) upper bound
    max_trajectories : hard cap on how many to export

    Returns
    -------
    (records, written_path)
        List of ExportRecord objects and the path they were written to (or None).
    """
    if cfg is None:
        cfg = ExportConfig(
            format=format,
            success_only=success_only,
            max_trajectories=max_trajectories,
        )
        if output_path:
            cfg.output_path = Path(output_path)
        if since:
            cfg.since_ts = datetime.datetime.fromisoformat(since).timestamp()
        if until:
            cfg.until_ts = datetime.datetime.fromisoformat(until).timestamp()

    # ── 1. Load trajectories ─────────────────────────────────────────────────
    where_clauses: list[str] = []
    params: list[Any] = []

    if cfg.success_only:
        where_clauses.append("t.is_success = 1")
    if cfg.since_ts:
        where_clauses.append("t.timestamp >= ?")
        params.append(cfg.since_ts)
    if cfg.until_ts:
        where_clauses.append("t.timestamp <= ?")
        params.append(cfg.until_ts)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    traj_rows = await db.fetch_all(
        f"SELECT * FROM trajectories {where_sql} "
        f"ORDER BY t.timestamp DESC LIMIT ?",
        params + [cfg.max_trajectories],
    )

    if not traj_rows:
        # Retry without the table alias "t." — some SQLite builds need it stripped
        traj_rows = await db.fetch_all(
            f"SELECT * FROM trajectories {where_sql.replace('t.', '')} "
            f"ORDER BY timestamp DESC LIMIT ?",
            params + [cfg.max_trajectories],
        )

    if not traj_rows:
        log.info("No trajectories found matching the export criteria.")
        return [], None

    # ── 2. Build benchmark bonus index + pull latest benchmark total ────────
    bonus_index = _build_scenario_index()

    # Latest benchmark run total (0-100 scale → 0-1) provides a global quality
    # signal that biases reward upward when the agent is performing well overall.
    _latest_bench_row = None
    try:
        _latest_bench_row = await db.fetch_one(
            "SELECT total_score FROM benchmark_history ORDER BY created_at DESC LIMIT 1"
        )
    except Exception:
        pass
    _global_bench_factor: float = (
        float(_latest_bench_row["total_score"]) / 100.0
        if _latest_bench_row and _latest_bench_row.get("total_score") is not None
        else 0.5  # neutral if no benchmark run yet
    )

    # ── 3. Build records ─────────────────────────────────────────────────────
    records: list[ExportRecord] = []

    for row in traj_rows:
        traj_id = row["trajectory_id"]
        steps = await db.fetch_all(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY step_order ASC",
            (traj_id,),
        )

        # Apply step count filter
        if len(steps) < cfg.min_steps or len(steps) > cfg.max_steps:
            continue

        is_success = bool(row["is_success"])
        task_desc  = row["task_description"]

        # Scenario-specific bonus (from BenchmarkScenario keyword index)
        scenario_bonus = _get_benchmark_bonus(task_desc, bonus_index)
        # Blend with global benchmark factor: 70% scenario-specific, 30% global
        bonus = 0.7 * scenario_bonus + 0.3 * _global_bench_factor

        reward = _compute_reward(is_success, [dict(s) for s in steps], cfg, bonus)

        rollout = _build_rollout_text(
            [dict(s) for s in steps], cfg.include_failed_steps
        )

        records.append(ExportRecord(
            trajectory_id   = traj_id,
            task_description= task_desc,
            prompt          = task_desc,
            completion      = rollout,
            reward          = reward,
            is_success      = is_success,
            total_tokens    = int(row.get("total_tokens") or 0),
            step_count      = len(steps),
            timestamp       = float(row.get("timestamp") or time.time()),
            metadata        = {
                "cumulative_latency_ms":  float(row.get("cumulative_latency") or 0.0),
                "benchmark_bonus":        round(bonus, 4),
                "scenario_bonus":         round(scenario_bonus, 4),
                "global_bench_factor":    round(_global_bench_factor, 4),
                "reward_breakdown": {
                    "outcome_component":    round(cfg.outcome_weight    * (1.0 if is_success else 0.0), 4),
                    "step_quality_component": round(cfg.step_quality_weight * (
                        sum(STEP_CATEGORY_SCORE.get(s.get("epistemic_category", "decision"), 0.5)
                            for s in [dict(x) for x in steps]) / max(len(steps), 1)
                    ), 4),
                    "benchmark_component":  round(cfg.benchmark_weight * bonus, 4),
                },
            },
        ))

    if not records:
        log.info("No records after filtering (%d trajectories scanned).", len(traj_rows))
        return [], None

    # ── 4. Compute GRPO advantages (reward − mean) / std ────────────────────
    if cfg.format == "grpo" and len(records) >= 2:
        rewards = [r.reward for r in records]
        mean_r  = sum(rewards) / len(rewards)
        var_r   = sum((x - mean_r) ** 2 for x in rewards) / len(rewards)
        std_r   = var_r ** 0.5 or 1.0
        for rec in records:
            rec.metadata["advantage"] = round((rec.reward - mean_r) / std_r, 4)

    # ── 5. Determine output path ─────────────────────────────────────────────
    written_path: Path | None = None

    if cfg.output_path is None:
        from silex.utils.config import KINTHIC_EXPORTS
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        ext = "csv" if cfg.format == "csv" else "jsonl"
        cfg.output_path = KINTHIC_EXPORTS / f"trajectories_{cfg.format}_{ts}.{ext}"

    cfg.output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── 6. Serialise ─────────────────────────────────────────────────────────
    if cfg.format == "csv":
        written_path = _write_csv(records, cfg.output_path)
    else:
        written_path = _write_jsonl(records, cfg.format, cfg.output_path)

    log.info(
        "Exported %d trajectories as %s → %s",
        len(records), cfg.format.upper(), written_path,
    )
    return records, written_path


def _write_jsonl(
    records: list[ExportRecord],
    fmt: Literal["sft", "grpo"],
    path: Path,
) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            obj = rec.to_sft() if fmt == "sft" else rec.to_grpo()
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _write_csv(records: list[ExportRecord], path: Path) -> Path:
    if not records:
        return path
    rows = [r.to_csv_row() for r in records]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path
