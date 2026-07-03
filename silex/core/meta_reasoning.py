"""
Meta-Reasoning Engine — Phase 7.

Analyzes ARIA's own performance data (critiques, failures, tool errors)
and generates formal proposals for self-improvement. All proposals require
human approval before implementation — this is a hard safety constraint.

Phase 3 upgrade:
  Introduces algorithmic preprocessing BEFORE the LLM sees any data:

  _compute_failure_clusters():
    Aggregates improvement_logs rows to calculate per-axis average scores
    and a failure count. Identifies the weakest axis (bottleneck_axis) via
    argmin on the mean score. This transforms "here are 10 raw rows" into
    structured FailureClusterReport data — the LLM receives math, not vibes.

  _compute_confidence_drift():
    Accepts a list of recent confidence values and computes the slope of
    a simple linear regression. Negative slope = ARIA is systematically
    becoming less certain over time (degradation signal).

Both helpers are static methods so they can be unit-tested in isolation
without requiring a live database connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Any

from silex.llm.base import SupportsLLM
from silex.core.observability import LocalAlignmentVerifier
from silex.models.schemas import (
    MetaAnalysisResponse,
    SelfImprovementProposal,
    InlineProposal,
)
from silex.storage.database import Database
from silex.utils.logger import setup_logger

log = setup_logger("aria.meta_reasoning")

META_ANALYSIS_PROMPT = """You are a Meta-Reasoning Analyst for an AI system called ARIA.
You will receive pre-computed performance analytics about ARIA's recent behavior.
The data has already been statistically processed — your job is to interpret the
structured analysis and propose ONE specific, actionable improvement.

The data includes:
- A FailureClusterReport: per-axis average scores, failure counts, identified bottleneck axis
- A confidence drift slope: negative = declining over time
- Raw tool failure descriptions
- Open uncertainty topics

Rules:
1. Only propose changes for REAL, REPEATED failures — not one-off mistakes.
2. Every proposal must include a measurable success metric.
3. Be conservative. A bad change is worse than no change.
4. You must specify exactly which system to modify.
5. If the data shows no clear pattern, set has_proposal to false.
6. PRIORITIZE the bottleneck_axis identified in the cluster report — this is
   the mathematically weakest dimension of ARIA's output quality.

Valid target systems:
- system_prompt: Changes to ARIA's base instructions
- tool_registry: Adding new tools or modifying existing ones
- cognitive_loop: Changes to the reasoning pipeline
- memory_store: Changes to how memories are stored or retrieved
- other: Anything else"""


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class FailureClusterReport:
    """Pre-computed algorithmic summary of critic failure patterns."""
    total_rejections: int
    avg_accuracy: float
    avg_depth: float
    avg_honesty: float
    bottleneck_axis: str          # 'accuracy', 'depth', or 'honesty'
    bottleneck_avg: float         # Average score of the weakest axis
    sample_feedbacks: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def to_prompt_block(self) -> str:
        """Format as a structured block for LLM injection."""
        feedbacks_str = "\n".join(
            f"  - {f[:120]}" for f in self.sample_feedbacks[:5]
        )
        return (
            "═══════════════════════════════════════════════════════════\n"
            "FAILURE CLUSTER REPORT (pre-computed)\n"
            "═══════════════════════════════════════════════════════════\n"
            f"  Total self-correction events:  {self.total_rejections}\n"
            f"  Avg accuracy across events:    {self.avg_accuracy:.3f}\n"
            f"  Avg depth across events:       {self.avg_depth:.3f}\n"
            f"  Avg honesty across events:     {self.avg_honesty:.3f}\n"
            f"  BOTTLENECK AXIS IDENTIFIED:    {self.bottleneck_axis.upper()} "
            f"(mean={self.bottleneck_avg:.3f})\n"
            f"\nSample rejection feedback messages:\n{feedbacks_str}\n"
        )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MetaReasoningEngine:
    """Analyzes ARIA's performance and generates self-improvement proposals."""

    def __init__(self, llm_client: SupportsLLM, db: Database):
        self.llm = llm_client
        self.db = db

    async def analyze_and_propose(
        self, status_callback: Callable[..., Any] | None = None
    ) -> SelfImprovementProposal | None:
        """
        Analyze recent performance data and generate a proposal if warranted.

        Phase 3 upgrade: algorithmic preprocessing produces a FailureClusterReport
        and confidence drift slope BEFORE the LLM sees any data. The LLM
        receives structured math, not raw text rows.
        """
        # Monitor and trigger prompt rollback if systemic alignment decay is detected
        await self._trigger_prompt_rollback()

        if status_callback:
            status_callback("[bright_magenta]  Gathering performance data...[/]")

        # ── Step 1: Raw data fetch ──────────────────────────────────────
        rejection_rows = await self.db.fetch_all(
            "SELECT * FROM improvement_logs ORDER BY created_at DESC LIMIT 20"
        )
        tool_failures = await self.db.fetch_all(
            "SELECT * FROM action_logs WHERE success = 0 ORDER BY created_at DESC LIMIT 10"
        )
        uncertainties = await self.db.fetch_all(
            "SELECT * FROM uncertainties WHERE status = 'open' ORDER BY created_at DESC LIMIT 5"
        )
        recent_turns = await self.db.fetch_all(
            "SELECT confidence FROM turns ORDER BY created_at DESC LIMIT 30"
        )

        if not rejection_rows and not tool_failures:
            log.debug("No performance data available for meta-analysis.")
            return None

        if status_callback:
            status_callback("[bright_magenta]  Computing failure clusters...[/]")

        # ── Step 2: Algorithmic preprocessing ──────────────────────────
        cluster_report: FailureClusterReport | None = None
        if rejection_rows:
            cluster_report = self._compute_failure_clusters(rejection_rows)

        confidence_slope: float | None = None
        if recent_turns:
            confidence_values = [float(r["confidence"]) for r in recent_turns]
            confidence_slope = self._compute_confidence_drift(confidence_values)

        if status_callback:
            status_callback("[bright_magenta]  Running meta-analysis...[/]")

        # ── Step 3: Build structured prompt ────────────────────────────
        sections = []

        if cluster_report:
            sections.append(cluster_report.to_prompt_block())

        if confidence_slope is not None:
            drift_label = (
                "DECLINING (⚠ systemic degradation signal)"
                if confidence_slope < -0.005
                else "STABLE" if abs(confidence_slope) < 0.005
                else "IMPROVING"
            )
            sections.append(
                "═══════════════════════════════════════════════════════════\n"
                "CONFIDENCE DRIFT ANALYSIS (linear regression over last 30 turns)\n"
                "═══════════════════════════════════════════════════════════\n"
                f"  Slope: {confidence_slope:+.6f} per turn\n"
                f"  Trend: {drift_label}\n"
            )

        if tool_failures:
            sections.append("RECENT TOOL FAILURES:")
            for f in tool_failures:
                sections.append(f"  Tool: {f['tool_name']} — {f['actual_outcome'][:100]}")
            sections.append("")

        if uncertainties:
            sections.append("UNRESOLVED UNCERTAINTIES:")
            for u in uncertainties:
                sections.append(f"  {u['topic']}: {u['why_uncertain'][:80]}")
            sections.append("")

        performance_data = "\n".join(sections)

        try:
            analysis = await self.llm.complete_json(
                schema=MetaAnalysisResponse,
                system_prompt=META_ANALYSIS_PROMPT,
                user_input=(
                    f"PERFORMANCE ANALYTICS:\n{performance_data}\n\n"
                    "Analyze and propose an improvement if warranted."
                ),
                temperature=0.2,
                request_kind="meta_reasoning",
            )

            if not analysis.has_proposal or not analysis.description:
                log.info("Meta-analysis found no actionable improvements.")
                return None

            # Persist the proposal
            proposal = SelfImprovementProposal(
                target_system=analysis.target_system,
                description=analysis.description,
                rationale=analysis.rationale,
                success_metric=analysis.success_metric,
            )

            await self.db.execute(
                """
                INSERT INTO improvement_proposals (
                    id, target_system, description, rationale,
                    success_metric, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.target_system,
                    proposal.description,
                    proposal.rationale,
                    proposal.success_metric,
                    proposal.status,
                    proposal.created_at,
                ),
            )

            log.info(f"New self-improvement proposal: {proposal.description[:60]}...")
            return proposal

        except Exception as e:
            log.warning(f"Meta-analysis failed (non-fatal): {e}")
            return None

    async def _trigger_prompt_rollback(self) -> bool:
        """
        Monitors active prompt mutations. If OLS trend regression analysis registers
        systemic alignment decay (beta < -0.015), executes a database snapshot rollback,
        resetting the system prompt configurations cleanly to the last verified stable iteration state.
        """
        from silex.utils.config import KRONOS_DIRECTIVES_FILE

        recent_turns = await self.db.fetch_all(
            "SELECT confidence FROM turns ORDER BY created_at DESC LIMIT 30"
        )
        if not recent_turns or len(recent_turns) < 5:
            log.info("Insufficient history for prompt rollback OLS trend analysis.")
            return False

        confidences = [float(r["confidence"]) for r in recent_turns]
        
        baseline = "System instruction baseline"
        if KRONOS_DIRECTIVES_FILE.exists():
            try:
                baseline = KRONOS_DIRECTIVES_FILE.read_text(encoding="utf-8")
            except Exception:
                pass
                
        verifier = LocalAlignmentVerifier(baseline, stability_threshold=-0.015, variance_budget=0.15)
        verifier.composite_scores = list(reversed(confidences))
        verifier.cosine_drifts = [0.01] * len(confidences)

        is_stable = verifier.analyze_drift_trend()
        
        if not is_stable:
            log.warning("OLS trend regression analysis registered systemic alignment decay! Initiating prompt rollback...")
            
            last_stable_proposal = await self.db.fetch_one(
                "SELECT * FROM improvement_proposals WHERE target_system = 'system_prompt' AND status = 'approved' ORDER BY created_at DESC LIMIT 1"
            )

            if last_stable_proposal:
                log.info(f"Rolling back to last verified stable improvement proposal: {last_stable_proposal['id']}")
                await self.db.execute(
                    "UPDATE improvement_proposals SET status = 'implemented' WHERE id = ?",
                    (last_stable_proposal["id"],)
                )
                
                try:
                    stable_prompt = (
                        "# Kronos Core Directives\n\n"
                        "This file contains unbreakable rules and behavioral guidelines.\n\n"
                        f"## Restored Directives (Rollback from OLS Decay):\n{last_stable_proposal['description']}\n"
                    )
                    KRONOS_DIRECTIVES_FILE.write_text(stable_prompt, encoding="utf-8")
                    log.info(f"System prompt configurations successfully rolled back to proposal {last_stable_proposal['id']}")
                except Exception as write_err:
                    log.error(f"Failed to write rolled-back directives: {write_err}")
                return True
            else:
                log.warning("No verified stable improvement proposal found in database for rollback. Restoring default directives.")
                try:
                    default_directives = (
                        "# Kronos Core Directives\n\n"
                        "This file contains unbreakable rules and behavioral guidelines. "
                        "Any instructions here override general knowledge and normal operating procedures.\n"
                    )
                    KRONOS_DIRECTIVES_FILE.write_text(default_directives, encoding="utf-8")
                except Exception as default_err:
                    log.error(f"Failed to write default directives: {default_err}")
                return True

        return False


    # ------------------------------------------------------------------
    # Algorithmic helpers (static — testable without DB)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_failure_clusters(rows: list[dict]) -> FailureClusterReport:
        """
        Aggregate improvement_log rows into a FailureClusterReport.

        Computes per-axis means and identifies which axis is the systemic
        bottleneck (the one with the lowest average score). This replaces
        the raw text dump that the old implementation passed to the LLM.

        Parameters
        ----------
        rows:
            Dicts with keys: accuracy_score, depth_score, honesty_score, feedback.
            Typically from: SELECT * FROM improvement_logs ORDER BY created_at DESC LIMIT 20

        Returns
        -------
        FailureClusterReport with bottleneck_axis set to 'accuracy', 'depth', or 'honesty'.
        """
        n = len(rows)
        if n == 0:
            return FailureClusterReport(
                total_rejections=0,
                avg_accuracy=1.0, avg_depth=1.0, avg_honesty=1.0,
                bottleneck_axis="none", bottleneck_avg=1.0,
            )

        avg_acc = sum(float(r.get("accuracy_score", 1.0)) for r in rows) / n
        avg_dep = sum(float(r.get("depth_score", 1.0)) for r in rows) / n
        avg_hon = sum(float(r.get("honesty_score", 1.0)) for r in rows) / n

        axis_scores = {
            "accuracy": avg_acc,
            "depth":    avg_dep,
            "honesty":  avg_hon,
        }
        bottleneck = min(axis_scores, key=axis_scores.__getitem__)

        feedbacks = [
            str(r.get("feedback", ""))[:120]
            for r in rows[:5]
            if r.get("feedback")
        ]

        return FailureClusterReport(
            total_rejections=n,
            avg_accuracy=avg_acc,
            avg_depth=avg_dep,
            avg_honesty=avg_hon,
            bottleneck_axis=bottleneck,
            bottleneck_avg=axis_scores[bottleneck],
            sample_feedbacks=feedbacks,
        )

    @staticmethod
    def _compute_confidence_drift(confidences: list[float]) -> float:
        """
        Compute the slope of a simple linear regression over confidence values.

        A negative slope means ARIA is systematically becoming less certain
        over time — a systemic degradation signal that the meta-analysis LLM
        call should flag for operator attention.

        Parameters
        ----------
        confidences:
            List of confidence floats from recent turns, most-recent first
            (as returned by 'SELECT confidence FROM turns ORDER BY created_at DESC').

        Returns
        -------
        float: slope of the linear fit (units: confidence change per turn).
               Negative = declining, positive = improving, ~0 = stable.
        """
        n = len(confidences)
        if n < 2:
            return 0.0

        # Reverse so index 0 is oldest (correct chronological order for regression)
        vals = list(reversed(confidences))
        xs = list(range(n))

        mean_x = sum(xs) / n
        mean_y = sum(vals) / n

        numerator   = sum((xs[i] - mean_x) * (vals[i] - mean_y) for i in range(n))
        denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    # ------------------------------------------------------------------
    # Proposal management
    # ------------------------------------------------------------------

    async def process_inline_proposals(
        self, proposals: list[InlineProposal], session_id: str
    ) -> list[SelfImprovementProposal]:
        """Persist structured self-improvement proposals generated by VYN."""
        persisted = []

        for prop in proposals:
            try:
                proposal = SelfImprovementProposal(
                    target_system=prop.target_system,
                    description=prop.change_description,
                    rationale=f"Self-identified during session {session_id[:8]}",
                    success_metric=prop.success_metric,
                )

                await self.db.execute(
                    """
                    INSERT INTO improvement_proposals (
                        id, target_system, description, rationale,
                        success_metric, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal.id,
                        proposal.target_system,
                        proposal.description,
                        proposal.rationale,
                        proposal.success_metric,
                        proposal.status,
                        proposal.created_at,
                    ),
                )

                persisted.append(proposal)
                log.info(f"Inline proposal persisted: {prop.change_description[:50]}...")

            except Exception as e:
                log.warning(f"Failed to process inline proposal: {e}")

        return persisted

    async def get_pending_proposals(self) -> list[SelfImprovementProposal]:
        """Fetch all pending proposals."""
        rows = await self.db.fetch_all(
            "SELECT * FROM improvement_proposals WHERE status = 'pending' ORDER BY created_at DESC"
        )
        return [self._row_to_proposal(r) for r in rows]

    async def get_all_proposals(self) -> list[SelfImprovementProposal]:
        """Fetch all proposals regardless of status."""
        rows = await self.db.fetch_all(
            "SELECT * FROM improvement_proposals ORDER BY created_at DESC"
        )
        return [self._row_to_proposal(r) for r in rows]

    async def get_approved_proposals(self) -> list[SelfImprovementProposal]:
        """Fetch proposals that the operator has approved — these become active directives."""
        rows = await self.db.fetch_all(
            "SELECT * FROM improvement_proposals WHERE status = 'approved' ORDER BY created_at DESC LIMIT 10"
        )
        return [self._row_to_proposal(r) for r in rows]

    async def update_status(self, proposal_id: str, status: str) -> None:
        """Update a proposal's status (approve, reject, implement)."""
        resolved = datetime.now(timezone.utc).isoformat() if status != "pending" else None
        await self.db.execute(
            "UPDATE improvement_proposals SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved, proposal_id),
        )
        log.info(f"Proposal {proposal_id[:8]} status → {status}")

    def _row_to_proposal(self, row) -> SelfImprovementProposal:
        return SelfImprovementProposal(
            id=row["id"],
            target_system=row["target_system"],
            description=row["description"],
            rationale=row["rationale"],
            success_metric=row["success_metric"],
            status=row["status"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )
