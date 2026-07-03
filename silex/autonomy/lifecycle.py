"""
Durable job lifecycle state machine for background autonomous goal execution.

Provides typed states, transitions, and idempotent helpers that the daemon
and CognitiveLoop.tick() use to durably execute goals across restarts.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    STEP_SAVED = "step_saved"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobEventKind(str, Enum):
    CREATED = "created"
    CLAIMED = "claimed"
    STEP_START = "step_start"
    STEP_DONE = "step_done"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    WORKER_SPAWN = "worker_spawn"
    WORKER_DONE = "worker_done"
    CHECKPOINT = "checkpoint"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class DurableJob:
    """Represents a single background autonomous goal execution."""

    goal_id: str
    description: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = JobStatus.PENDING.value
    idempotency_key: str = ""
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: float = 3600.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    last_heartbeat: Optional[float] = None
    output_summary: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            self.idempotency_key = hashlib.sha256(
                f"{self.goal_id}:{self.description}".encode()
            ).hexdigest()[:32]

    def is_expired(self) -> bool:
        if self.started_at is None:
            return False
        return time.time() - self.started_at > self.timeout_seconds

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class JobEvent:
    """A single immutable event in the goal execution event stream."""

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    goal_id: str = ""
    run_id: str = ""
    kind: str = JobEventKind.CREATED.value
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def payload_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
