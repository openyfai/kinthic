"""
Memory Store — ARIA's persistent knowledge.

Handles storing, retrieving, searching, and managing memories in SQLite.
The retrieval strategy uses three pools: recency, importance, and relevance.

Polish additions:
  - Duplicate detection before storing
  - Memory deletion (forget)
  - Memory search command
  - Manual memory injection
  - Importance decay over time
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from aria.models.schemas import Memory, MemorySource
from aria.storage.database import Database
from aria.utils.config import (
    MAX_IMPORTANT_MEMORIES,
    MAX_RECENT_MEMORIES,
    MAX_RELEVANT_MEMORIES,
)
from aria.utils.logger import setup_logger

log = setup_logger("aria.memory")


class MemoryStore:
    """SQLite-backed persistent memory for ARIA."""

    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(self, memory: Memory) -> Memory:
        """Store a new memory (with duplicate detection)."""
        # Check for duplicates — skip if a very similar memory exists
        if await self._is_duplicate(memory.content):
            log.debug(f"Skipped duplicate memory: {memory.content[:40]}...")
            return memory

        await self.db.execute(
            """
            INSERT INTO memories (id, content, source, importance, created_at,
                                  last_accessed, access_count, tags, related_memories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.source.value if isinstance(memory.source, MemorySource) else memory.source,
                memory.importance,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                json.dumps(memory.tags),
                json.dumps(memory.related_memories),
            ),
        )
        log.debug(f"Stored memory: {memory.content[:60]}...")
        return memory

    async def get(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID."""
        row = await self.db.fetch_one(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        if row is None:
            return None
        return self._row_to_memory(row)

    async def get_by_index(self, index: int) -> Memory | None:
        """Retrieve a memory by its display index (1-based, sorted by importance)."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC"
        )
        if 1 <= index <= len(rows):
            return self._row_to_memory(rows[index - 1])
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        row = await self.db.fetch_one(
            "SELECT content FROM memories WHERE id = ?", (memory_id,)
        )
        if row is None:
            return False
        await self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        log.info(f"Deleted memory: {row['content'][:40]}...")
        return True

    async def delete_by_index(self, index: int) -> bool:
        """Delete a memory by its display index (1-based)."""
        memory = await self.get_by_index(index)
        if memory:
            return await self.delete(memory.id)
        return False

    async def update_access(self, memory_id: str) -> None:
        """Mark a memory as accessed (updates timestamp and counter)."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE memories
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ?
            """,
            (now, memory_id),
        )

    async def count(self) -> int:
        """Get total memory count."""
        row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM memories")
        return row["cnt"] if row else 0

    async def all_memories(self) -> list[Memory]:
        """Retrieve all memories (use sparingly)."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC"
        )
        return [self._row_to_memory(r) for r in rows]

    async def search(self, query: str) -> list[Memory]:
        """Search memories by keyword (for the :search command)."""
        return await self._search_relevant(query, limit=50)

    async def add_manual(self, content: str, importance: float = 0.5) -> Memory:
        """Add a memory manually from user command."""
        memory = Memory(
            content=content,
            source=MemorySource.USER,
            importance=importance,
            tags=["manual"],
        )
        # Bypass duplicate check for manual memories — user explicitly wants it
        await self.db.execute(
            """
            INSERT INTO memories (id, content, source, importance, created_at,
                                  last_accessed, access_count, tags, related_memories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.source.value,
                memory.importance,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                json.dumps(memory.tags),
                json.dumps(memory.related_memories),
            ),
        )
        log.info(f"Manual memory stored: {content[:40]}...")
        return memory

    # ------------------------------------------------------------------
    # Retrieval Strategy
    # ------------------------------------------------------------------

    async def retrieve_context(self, query: str = "") -> list[Memory]:
        """
        Retrieve memories for context injection using the three-pool strategy:
          1. Recent — last N accessed memories (short-term recall)
          2. Important — top N by importance (core knowledge)
          3. Relevant — keyword match against query (situational)

        Results are deduplicated and sorted by importance.
        """
        seen_ids: set[str] = set()
        result: list[Memory] = []

        # Pool 1: Recent
        recent = await self._get_recent(MAX_RECENT_MEMORIES)
        for m in recent:
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                result.append(m)

        # Pool 2: Important
        important = await self._get_important(MAX_IMPORTANT_MEMORIES)
        for m in important:
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                result.append(m)

        # Pool 3: Relevant (keyword search)
        if query.strip():
            relevant = await self._search_relevant(query, MAX_RELEVANT_MEMORIES)
            for m in relevant:
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    result.append(m)

        # Sort by importance descending
        result.sort(key=lambda m: m.importance, reverse=True)

        # Update access timestamps for retrieved memories
        for m in result:
            await self.update_access(m.id)

        log.debug(f"Retrieved {len(result)} memories for context")
        return result

    async def _get_recent(self, limit: int) -> list[Memory]:
        """Get most recently accessed memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(r) for r in rows]

    async def _get_important(self, limit: int) -> list[Memory]:
        """Get highest importance memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(r) for r in rows]

    async def _search_relevant(self, query: str, limit: int) -> list[Memory]:
        """
        Simple keyword relevance search.

        This is intentionally basic — Phase 2 replaces this with
        graph-based traversal and/or embedding similarity.
        """
        # Split query into keywords and search for any match
        keywords = [kw.strip().lower() for kw in query.split() if len(kw.strip()) > 2]
        if not keywords:
            return []

        # Build a LIKE query for each keyword
        conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in keywords])
        params = tuple(f"%{kw}%" for kw in keywords)

        rows = await self.db.fetch_all(
            f"SELECT * FROM memories WHERE {conditions} ORDER BY importance DESC LIMIT ?",
            (*params, limit),
        )
        return [self._row_to_memory(r) for r in rows]

    # ------------------------------------------------------------------
    # Duplicate Detection
    # ------------------------------------------------------------------

    async def _is_duplicate(self, content: str) -> bool:
        """
        Check if a very similar memory already exists.

        Uses normalized substring matching — if 80%+ of the words match
        an existing memory, consider it a duplicate.
        """
        content_lower = content.lower().strip()
        content_words = set(content_lower.split())

        if not content_words:
            return False

        # Check against recent memories (don't scan entire DB)
        recent = await self._get_recent(50)
        for mem in recent:
            existing_words = set(mem.content.lower().strip().split())
            if not existing_words:
                continue

            # Calculate word overlap
            overlap = content_words & existing_words
            smaller = min(len(content_words), len(existing_words))

            if smaller > 0 and len(overlap) / smaller >= 0.8:
                return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_memory(row: dict) -> Memory:
        """Convert a database row to a Memory model."""
        return Memory(
            id=row["id"],
            content=row["content"],
            source=row["source"],
            importance=row["importance"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            tags=json.loads(row["tags"]),
            related_memories=json.loads(row["related_memories"]),
        )
