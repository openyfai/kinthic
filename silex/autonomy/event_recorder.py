"""
Durable event recorder for background goal execution.

Appends every meaningful action, step, approval, worker event, and outcome
to the `job_events` SQLite table so execution is replayable and auditable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from silex.autonomy.lifecycle import JobEvent, JobEventKind

log = logging.getLogger("silex.autonomy.event_recorder")


class EventRecorder:
    """
    Writes durable events to the database for a specific goal/run.
    Injected into the cognitive loop and tool registry during autonomous execution.
    """

    def __init__(self, db: Any, goal_id: str, run_id: str) -> None:
        self._db = db
        self.goal_id = goal_id
        self.run_id = run_id

    async def record(
        self,
        kind: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> str:
        event = JobEvent(
            goal_id=self.goal_id,
            run_id=self.run_id,
            kind=kind,
            payload=payload or {},
        )
        try:
            await self._db.execute(
                """
                INSERT OR IGNORE INTO job_events
                    (event_id, goal_id, run_id, kind, payload_json, payload_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.goal_id,
                    event.run_id,
                    event.kind,
                    json.dumps(event.payload, default=str),
                    event.payload_hash(),
                    event.timestamp,
                ),
            )
        except Exception as exc:
            log.warning("EventRecorder write failed: %s", exc)
        return event.event_id

    async def record_tool(self, tool_name: str, args: dict[str, Any], result: str, success: bool) -> None:
        await self.record(
            JobEventKind.TOOL_CALL.value,
            {"tool": tool_name, "args": args, "result": result[:512], "success": success},
        )

    async def record_worker_spawn(self, worker_id: str, objective: str) -> None:
        await self.record(
            JobEventKind.WORKER_SPAWN.value,
            {"worker_id": worker_id, "objective": objective},
        )

    async def record_worker_done(self, worker_id: str, exit_code: int, success: bool) -> None:
        await self.record(
            JobEventKind.WORKER_DONE.value,
            {"worker_id": worker_id, "exit_code": exit_code, "success": success},
        )

    async def record_approval_requested(self, approval_id: str, tool_name: str, risk_level: str) -> None:
        await self.record(
            JobEventKind.APPROVAL_REQUESTED.value,
            {"approval_id": approval_id, "tool": tool_name, "risk_level": risk_level},
        )

    async def record_approval_resolved(self, approval_id: str, approved: bool) -> None:
        await self.record(
            JobEventKind.APPROVAL_RESOLVED.value,
            {"approval_id": approval_id, "approved": approved},
        )

    async def record_checkpoint(self, superstep: int, summary: str) -> None:
        await self.record(
            JobEventKind.CHECKPOINT.value,
            {"superstep": superstep, "summary": summary[:1024]},
        )

    async def record_step(self, step_order: int, action: str, output: str, latency_ms: float, tokens: int) -> None:
        await self.record(
            JobEventKind.STEP_DONE.value,
            {
                "step_order": step_order,
                "action": action,
                "output": output[:512],
                "latency_ms": latency_ms,
                "tokens": tokens,
            },
        )

    async def update_heartbeat(self) -> None:
        """Refresh last_heartbeat for the running job."""
        try:
            await self._db.execute(
                "UPDATE autonomous_jobs SET last_heartbeat = ? WHERE goal_id = ? AND run_id = ?",
                (time.time(), self.goal_id, self.run_id),
            )
        except Exception as exc:
            log.debug("Heartbeat update failed: %s", exc)
