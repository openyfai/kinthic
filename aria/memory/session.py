"""
Session Manager — ARIA's continuity tracker.

Manages conversation sessions, turn history, and aggregate stats.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from aria.models.schemas import Session, Turn
from aria.storage.database import Database
from aria.utils.logger import setup_logger

log = setup_logger("aria.session")


class SessionManager:
    """Tracks conversation sessions and turn history."""

    def __init__(self, db: Database):
        self.db = db
        self._current: Session | None = None

    @property
    def current(self) -> Session | None:
        return self._current

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def start_session(self) -> Session:
        """Begin a new conversation session."""
        session = Session()
        await self.db.execute(
            """
            INSERT INTO sessions (id, started_at, turn_count, memories_created,
                                  goals_modified, avg_confidence, topics)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.started_at,
                session.turn_count,
                session.memories_created,
                session.goals_modified,
                session.avg_confidence,
                json.dumps(session.topics),
            ),
        )
        self._current = session
        log.info(f"Started session {session.id[:8]}...")
        return session

    async def end_session(self) -> None:
        """End the current session."""
        if self._current is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (now, self._current.id),
        )
        log.info(f"Ended session {self._current.id[:8]}...")
        self._current = None

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    async def record_turn(
        self,
        user_input: str,
        reasoning: str,
        response: str,
        self_reflection: str,
        confidence: float,
        memories_added: int = 0,
        goals_changed: int = 0,
    ) -> Turn:
        """Record a conversation turn and update session stats."""
        if self._current is None:
            raise RuntimeError("No active session. Call start_session() first.")

        self._current.turn_count += 1
        self._current.memories_created += memories_added
        self._current.goals_modified += goals_changed

        # Running average of confidence
        n = self._current.turn_count
        prev_avg = self._current.avg_confidence
        self._current.avg_confidence = prev_avg + (confidence - prev_avg) / n

        turn = Turn(
            session_id=self._current.id,
            turn_number=self._current.turn_count,
            user_input=user_input,
            reasoning=reasoning,
            response=response,
            self_reflection=self_reflection,
            confidence=confidence,
        )

        # Store the turn
        await self.db.execute(
            """
            INSERT INTO turns (id, session_id, turn_number, user_input,
                               reasoning, response, self_reflection, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.id,
                turn.session_id,
                turn.turn_number,
                turn.user_input,
                turn.reasoning,
                turn.response,
                turn.self_reflection,
                turn.confidence,
                turn.created_at,
            ),
        )

        # Update session stats
        await self.db.execute(
            """
            UPDATE sessions
            SET turn_count = ?, memories_created = ?, goals_modified = ?, avg_confidence = ?
            WHERE id = ?
            """,
            (
                self._current.turn_count,
                self._current.memories_created,
                self._current.goals_modified,
                self._current.avg_confidence,
                self._current.id,
            ),
        )

        return turn

    async def get_recent_turns(self, limit: int = 10) -> list[Turn]:
        """Get the most recent turns from the current session."""
        if self._current is None:
            return []

        rows = await self.db.fetch_all(
            """
            SELECT * FROM turns
            WHERE session_id = ?
            ORDER BY turn_number DESC
            LIMIT ?
            """,
            (self._current.id, limit),
        )

        turns = [self._row_to_turn(r) for r in rows]
        turns.reverse()  # Chronological order
        return turns

    async def get_all_sessions(self) -> list[Session]:
        """Get all past sessions."""
        rows = await self.db.fetch_all(
            "SELECT * FROM sessions ORDER BY started_at DESC"
        )
        return [self._row_to_session(r) for r in rows]

    async def get_total_turns(self) -> int:
        """Get total turns across all sessions."""
        row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM turns")
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_turn(row: dict) -> Turn:
        return Turn(
            id=row["id"],
            session_id=row["session_id"],
            turn_number=row["turn_number"],
            user_input=row["user_input"],
            reasoning=row["reasoning"],
            response=row["response"],
            self_reflection=row["self_reflection"],
            confidence=row["confidence"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_session(row: dict) -> Session:
        return Session(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            turn_count=row["turn_count"],
            memories_created=row["memories_created"],
            goals_modified=row["goals_modified"],
            avg_confidence=row["avg_confidence"],
            topics=json.loads(row["topics"]),
        )
