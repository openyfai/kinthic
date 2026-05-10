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
from math import exp

from aria.models.schemas import Memory, MemorySource, MemoryType
from aria.storage.database import Database
from aria.utils.config import (
    MAX_IMPORTANT_MEMORIES,
    MAX_RECENT_MEMORIES,
    MAX_RELEVANT_MEMORIES,
)
from aria.memory.vector_store import VectorStore
from aria.utils.logger import setup_logger

log = setup_logger("aria.memory")


class MemoryStore:
    """SQLite-backed persistent memory for ARIA."""

    def __init__(self, db: Database):
        self.db = db
        self.vs = VectorStore(collection_name="aria_memories")

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
            INSERT INTO memories (id, content, source, memory_type, importance,
                                  confidence, created_at, last_accessed,
                                  access_count, tags, provenance_json,
                                  related_memories, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.source.value if isinstance(memory.source, MemorySource) else memory.source,
                memory.memory_type.value if isinstance(memory.memory_type, MemoryType) else memory.memory_type,
                memory.importance,
                memory.confidence,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                json.dumps(memory.tags),
                json.dumps(memory.provenance),
                json.dumps(memory.related_memories),
                memory.archived_at,
            ),
        )
        if self.vs.is_active:
            type_val = memory.memory_type.value if isinstance(memory.memory_type, MemoryType) else memory.memory_type
            self.vs.add_chunks([memory.content], [{"type": type_val}], ids=[memory.id])

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
            INSERT INTO memories (id, content, source, memory_type, importance,
                                  confidence, created_at, last_accessed,
                                  access_count, tags, provenance_json,
                                  related_memories, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.source.value,
                memory.memory_type.value,
                memory.importance,
                memory.confidence,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                json.dumps(memory.tags),
                json.dumps(memory.provenance),
                json.dumps(memory.related_memories),
                memory.archived_at,
            ),
        )
        if self.vs.is_active:
            type_val = memory.memory_type.value if isinstance(memory.memory_type, MemoryType) else memory.memory_type
            self.vs.add_chunks([memory.content], [{"type": type_val}], ids=[memory.id])

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

        Results are deduplicated and sorted by a fused trust/relevance score.
        """
        candidates: dict[str, Memory] = {}

        # Pool 1: Recent
        recent = await self._get_recent(MAX_RECENT_MEMORIES)
        for m in recent:
            candidates[m.id] = m

        # Pool 2: Important
        important = await self._get_important(MAX_IMPORTANT_MEMORIES)
        for m in important:
            candidates[m.id] = m

        # Pool 3: Relevant (keyword search)
        if query.strip():
            relevant = await self._search_relevant(query, MAX_RELEVANT_MEMORIES)
            for m in relevant:
                candidates[m.id] = m

        # Pool 4: Semantic (vector search)
        if query.strip() and self.vs.is_active:
            semantic_results = self.vs.search(query, MAX_RELEVANT_MEMORIES)
            semantic_ids = [res["id"] for res in semantic_results if res.get("id")]
            if semantic_ids:
                placeholders = ",".join("?" * len(semantic_ids))
                rows = await self.db.fetch_all(
                    f"SELECT * FROM memories WHERE id IN ({placeholders}) AND archived_at IS NULL",
                    tuple(semantic_ids)
                )
                for row in rows:
                    m = self._row_to_memory(row)
                    candidates[m.id] = m

        result = sorted(
            candidates.values(),
            key=lambda m: self._retrieval_score(m, query),
            reverse=True,
        )

        # Update access timestamps for retrieved memories
        for m in result:
            await self.update_access(m.id)

        log.debug(f"Retrieved {len(result)} memories for context")
        return result

    async def _get_recent(self, limit: int) -> list[Memory]:
        """Get most recently accessed memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories WHERE archived_at IS NULL ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(r) for r in rows]

    async def _get_important(self, limit: int) -> list[Memory]:
        """Get highest importance memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories WHERE archived_at IS NULL ORDER BY importance DESC LIMIT ?",
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
            f"SELECT * FROM memories WHERE archived_at IS NULL AND ({conditions}) ORDER BY importance DESC LIMIT ?",
            (*params, limit),
        )
        return [self._row_to_memory(r) for r in rows]

    @staticmethod
    def _retrieval_score(memory: Memory, query: str) -> float:
        """Fuse importance, reliability, recency, relevance, and source trust."""
        query_words = {w.lower() for w in query.split() if len(w) > 2}
        content_words = {w.lower() for w in memory.content.split() if len(w) > 2}
        relevance = 0.0
        if query_words:
            relevance = len(query_words & content_words) / max(len(query_words), 1)

        try:
            last_accessed = datetime.fromisoformat(memory.last_accessed)
            age_days = max((datetime.now(timezone.utc) - last_accessed).days, 0)
            recency = exp(-age_days / 30)
        except Exception:
            recency = 0.5

        source_trust = {
            MemorySource.USER: 0.9,
            MemorySource.SYSTEM: 0.85,
            MemorySource.REFLECTION: 0.65,
            MemorySource.INFERENCE: 0.55,
        }.get(memory.source, 0.5)

        type_bonus = {
            MemoryType.PREFERENCE: 0.08,
            MemoryType.PROCEDURAL: 0.06,
            MemoryType.PROJECT: 0.06,
            MemoryType.NORMATIVE: 0.10,
            MemoryType.CHARACTER: 0.09,
        }.get(memory.memory_type, 0.0)

        return (
            memory.importance * 0.35
            + memory.confidence * 0.20
            + relevance * 0.25
            + recency * 0.10
            + source_trust * 0.10
            + type_bonus
        )

    # ------------------------------------------------------------------
    # Duplicate Detection
    # ------------------------------------------------------------------

    async def _is_duplicate(self, content: str) -> bool:
        """
        Check if a very similar memory already exists.
        
        Uses vector semantic similarity to catch rephrased facts.
        Falls back to word overlap if VectorStore is offline.
        """
        if self.vs.is_active:
            results = self.vs.search(content, n_results=1)
            # Distance < 0.2 typically indicates semantic equivalence with MiniLM
            if results and results[0].get("distance", 1.0) < 0.2:
                return True
            return False

        content_lower = content.lower().strip()
        content_words = set(content_lower.split())

        if not content_words:
            return False

        # Fallback: Check against recent memories
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

    async def archive(self, memory_id: str) -> bool:
        """Soft-archive a memory without destroying provenance."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE memories SET archived_at = ? WHERE id = ?",
            (now, memory_id),
        )
        return True

    async def update_confidence(self, memory_id: str, confidence: float) -> bool:
        """Adjust memory confidence for correction workflows."""
        confidence = max(0.0, min(1.0, confidence))
        await self.db.execute(
            "UPDATE memories SET confidence = ? WHERE id = ?",
            (confidence, memory_id),
        )
        return True

    async def merge(self, keep_id: str, merge_id: str) -> bool:
        """Merge two memories by archiving the duplicate and linking provenance."""
        keep = await self.get(keep_id)
        duplicate = await self.get(merge_id)
        if not keep or not duplicate:
            return False
        related = set(keep.related_memories)
        related.add(merge_id)
        provenance = dict(keep.provenance)
        provenance.setdefault("merged_memory_ids", [])
        provenance["merged_memory_ids"].append(merge_id)
        await self.db.execute(
            "UPDATE memories SET related_memories = ?, provenance_json = ? WHERE id = ?",
            (json.dumps(sorted(related)), json.dumps(provenance), keep_id),
        )
        await self.archive(merge_id)
        return True

    async def decay_importance(self, days: int = 7, decay_factor: float = 0.95):
        """Multiplies importance by decay_factor for memories not accessed in the last `days`."""
        await self.db.execute(
            """
            UPDATE memories
            SET importance = importance * ?
            WHERE (julianday('now') - julianday(last_accessed)) > ?
              AND archived_at IS NULL
            """,
            (decay_factor, days)
        )
        log.info(f"Decayed importance of memories untouched in {days} days by factor {decay_factor}.")

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
            memory_type=row.get("memory_type", "semantic"),
            importance=row["importance"],
            confidence=row.get("confidence", 0.5),
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            tags=json.loads(row["tags"]),
            provenance=json.loads(row.get("provenance_json", "{}")),
            related_memories=json.loads(row["related_memories"]),
            archived_at=row.get("archived_at"),
        )
    # ------------------------------------------------------------------
    # Semantic Profiles (Phase 7)
    # ------------------------------------------------------------------

    async def get_semantic_profile(self, term: str) -> dict | None:
        """Retrieve the objective mapping for a subjective term."""
        row = await self.db.fetch_one(
            "SELECT * FROM semantic_profiles WHERE term = ?", (term.lower(),)
        )
        if row:
            return {
                "term": row["term"],
                "objective_proxies": json.loads(row["objective_proxies"]),
                "context_tags": json.loads(row["context_tags"]),
                "confidence": row["confidence"],
                "updated_at": row["updated_at"]
            }
        return None

    async def save_semantic_profile(self, term: str, objective_proxies: list[str], confidence: float = 0.5):
        """Save or update a semantic profile."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO semantic_profiles (term, objective_proxies, confidence, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                objective_proxies = excluded.objective_proxies,
                confidence = excluded.confidence,
                updated_at = excluded.updated_at
            """,
            (term.lower(), json.dumps(objective_proxies), confidence, now)
        )

    async def get_all_semantic_profiles(self) -> dict[str, list[str]]:
        """Retrieve all learned semantic mappings."""
        rows = await self.db.fetch_all("SELECT term, objective_proxies FROM semantic_profiles")
        return {row["term"]: json.loads(row["objective_proxies"]) for row in rows}
