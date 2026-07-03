"""
Stuck-loop detector for autonomous background job execution.

Analyzes the event stream for repeated action+observation hashes
(per the research) and detects stale heartbeats / timeout violations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

log = logging.getLogger("silex.autonomy.watchdog")

CONSECUTIVE_REPEATS_THRESHOLD = 4
DEFAULT_HEARTBEAT_STALE_SECONDS = 600.0
DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0


class StuckLoopDetector:
    """
    Analyzes the last N events in job_events to detect repeating loops.
    Returns True (stuck) if the same action+result pair repeats >= 4 times.
    """

    def __init__(self, window: int = 8) -> None:
        self.window = window

    async def is_stuck(self, db: Any, goal_id: str, run_id: str) -> bool:
        try:
            rows = await db.fetch_all(
                """
                SELECT kind, payload_json FROM job_events
                WHERE goal_id = ? AND run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (goal_id, run_id, self.window),
            )
        except Exception as exc:
            log.debug("StuckLoopDetector query failed: %s", exc)
            return False

        if len(rows) < CONSECUTIVE_REPEATS_THRESHOLD:
            return False

        def _hash_row(row: dict) -> str:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            combined = f'{row["kind"]}:{json.dumps(payload, sort_keys=True, default=str)}'
            return hashlib.sha256(combined.encode()).hexdigest()[:12]

        hashes = [_hash_row(dict(r)) for r in rows]
        top = hashes[0]
        repeats = sum(1 for h in hashes[:CONSECUTIVE_REPEATS_THRESHOLD] if h == top)
        if repeats >= CONSECUTIVE_REPEATS_THRESHOLD:
            log.warning(
                "StuckLoopDetector: goal=%s run=%s — %d consecutive identical events detected",
                goal_id,
                run_id,
                repeats,
            )
            return True
        return False

    async def check_stale_heartbeat(
        self,
        db: Any,
        stale_threshold: float = DEFAULT_HEARTBEAT_STALE_SECONDS,
    ) -> list[dict]:
        """Return running jobs whose last_heartbeat is older than the threshold."""
        try:
            rows = await db.fetch_all(
                """
                SELECT goal_id, run_id, description, last_heartbeat, started_at, timeout_seconds
                FROM autonomous_jobs
                WHERE status IN ('running', 'claimed')
                """,
            )
        except Exception as exc:
            log.debug("Heartbeat check query failed: %s", exc)
            return []

        now = time.time()
        stale = []
        for r in rows:
            row = dict(r)
            last_hb = row.get("last_heartbeat") or row.get("started_at") or 0
            if last_hb and (now - float(last_hb)) > stale_threshold:
                stale.append(row)
            timeout = float(row.get("timeout_seconds") or DEFAULT_JOB_TIMEOUT_SECONDS)
            started = row.get("started_at") or 0
            if started and (now - float(started)) > timeout:
                stale.append(row)
        return stale
