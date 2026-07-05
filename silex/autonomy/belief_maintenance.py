"""
Scheduled belief-maintenance worker.

Runs periodically to:
1. Identify top unresolved contradictions
2. Schedule a debate/verification turn using the CognitiveLoop
3. Feed outcomes back into proposition_beliefs via BeliefEngine
4. Mark resolved contradictions and hypotheses

Research basis: Engineering Epistemic Integrity (2026)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("silex.autonomy.belief_maintenance")

DEFAULT_MAINTENANCE_INTERVAL = 1800.0  # 30 minutes
MAX_CONTRADICTIONS_PER_CYCLE = 3


class BeliefMaintenanceScheduler:
    """
    Background task that resolves contradictions and verifies stale beliefs
    by running targeted cognitive turns via the DebateEngine or tool calls.
    """

    def __init__(
        self,
        db: Any,
        cognitive_loop: Any,
        interval: float = DEFAULT_MAINTENANCE_INTERVAL,
    ) -> None:
        self._db = db
        self._loop = cognitive_loop
        self.interval = interval
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("BeliefMaintenanceScheduler started (interval=%.0fs)", self.interval)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                if self._running:
                    await self._maintenance_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("BeliefMaintenanceScheduler error: %s", exc)

    async def _maintenance_cycle(self) -> None:
        from silex.world.belief_engine import BeliefEngine

        engine = BeliefEngine(self._db)

        # 1. Resolve top unresolved contradictions
        contradictions = await engine.get_unresolved_contradictions(
            MAX_CONTRADICTIONS_PER_CYCLE
        )
        for contradiction in contradictions:
            await self._resolve_contradiction(engine, contradiction)

        # 2. Verify stale uncertain beliefs
        stale = await engine.get_stale_beliefs(stale_seconds=86400.0, limit=5)
        for belief in stale:
            await self._verify_belief(engine, belief)

    async def _resolve_contradiction(
        self, engine: Any, contradiction: dict[str, Any]
    ) -> None:
        claim_a = contradiction.get("claim_a", "")
        claim_b = contradiction.get("claim_b", "")
        description = contradiction.get("description", "")

        if not claim_a or not claim_b:
            return

        try:
            from silex.core.debate import DebateEngine

            debate = DebateEngine(self._loop.llm)
            verdict = await debate.run(
                proposition_a=claim_a,
                proposition_b=claim_b,
                context=description,
            )
            winner_claim = verdict.get("winner_claim", "")
            confidence = float(verdict.get("confidence", 0.6))

            if winner_claim:
                await engine.update_belief(
                    winner_claim, "true", confidence, source="debate_engine"
                )
                loser = claim_b if winner_claim == claim_a else claim_a
                await engine.update_belief(
                    loser, "false", 1.0 - confidence, source="debate_engine"
                )

            # Mark contradiction resolved
            await self._db.execute(
                "UPDATE contradictions SET status='resolved' WHERE id=?",
                (contradiction.get("id", ""),),
            )
            log.info(
                "Resolved contradiction: %s vs %s → %s",
                claim_a[:60],
                claim_b[:60],
                winner_claim[:60],
            )
        except Exception as exc:
            log.debug("Contradiction resolution failed: %s", exc)

    async def _verify_belief(self, engine: Any, belief: dict[str, Any]) -> None:
        claim = belief.get("claim", "")
        if not claim:
            return

        try:
            prompt = (
                f"Verify the following claim using your tools and knowledge:\n\n"
                f'CLAIM: "{claim}"\n\n'
                f"Use a web search or memory search to gather evidence. "
                f"Then output EXACTLY one of: VERIFIED_TRUE, VERIFIED_FALSE, or STILL_UNCERTAIN, "
                f"followed by a confidence score 0.0-1.0."
            )
            response = await self._loop.process(prompt)
            raw = getattr(response, "response", str(response)).upper()

            stance = "uncertain"
            confidence = 0.5
            if "VERIFIED_TRUE" in raw:
                stance = "true"
                confidence = 0.8
            elif "VERIFIED_FALSE" in raw:
                stance = "false"
                confidence = 0.8

            import re

            conf_match = re.search(r"(\d+\.\d+)", raw)
            if conf_match:
                confidence = float(conf_match.group(1))

            await engine.update_belief(
                claim, stance, confidence, source="scheduled_verification"
            )
            log.debug(
                "Verified belief '%s...' → %s (conf=%.2f)",
                claim[:50],
                stance,
                confidence,
            )
        except Exception as exc:
            log.debug("Belief verification failed: %s", exc)
