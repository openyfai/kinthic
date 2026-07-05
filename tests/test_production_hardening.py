"""
Verification tests for the Kinthic production-hardening plan
(kinthic_production_hardening_300c3294.plan.md).

Grouped by the phase that introduced the guarantee being tested:

  - Security (A1/A2): gateway auth middleware, host-fallback allowlist/env scrubbing.
  - Crash-injection (A3/A5): a vector-store failure after a committed SQLite
    write must not lose or corrupt the SQLite row, and reconcile must heal it.
  - Concurrency (B6/B7/C13): parallel writes through the single writer queue
    must not deadlock/corrupt state; a saturated write queue must shed
    (fail fast) instead of hanging forever.
  - Corrupt-row (A4): malformed JSON/timestamps in a memory row must not
    crash retrieval — the row is skipped, the rest of the batch survives.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest


class FakeVectorStore:
    """In-memory stand-in for ChromaDB's PersistentClient collection.

    Supports the subset of VectorStore's surface MemoryStore relies on, plus
    a `fail_next_add` knob to simulate a vector-store crash right after a
    SQLite commit for crash-injection testing.
    """

    def __init__(self):
        self.is_active = True
        self._docs: dict[str, str] = {}
        self.fail_next_add = False
        self.add_calls = 0
        self.delete_calls = 0
        self.canned_search_results: list[dict] = []

        class _Collection:
            def __init__(self, outer):
                self._outer = outer

            def get(self, include=None):
                return {"ids": list(self._outer._docs.keys())}

        self.collection = _Collection(self)

    def add_chunks(self, texts, metadatas, ids=None):
        self.add_calls += 1
        if self.fail_next_add:
            self.fail_next_add = False
            raise RuntimeError("simulated ChromaDB crash after SQLite commit")
        for i, doc_id in enumerate(ids or []):
            self._docs[doc_id] = texts[i]

    def search(self, query, n_results=5):
        return self.canned_search_results

    def delete_by_ids(self, ids):
        self.delete_calls += 1
        for i in ids:
            self._docs.pop(i, None)


async def _make_memory_store(tmp_path: Path, name: str = "test.db"):
    from silex.storage.database import Database
    from silex.memory.memory_store import MemoryStore

    db = Database(str(tmp_path / name))
    await db.connect()
    store = MemoryStore(db)
    store.vs = FakeVectorStore()
    return db, store


# ── A1: Gateway auth middleware ────────────────────────────────────────────


class TestGatewayAuthMiddleware:
    """Prove that mutating/state-revealing routes require the web API key,
    while the health check stays public, regardless of Origin/CORS config."""

    def _build_app(self):
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from silex.api.server import LocalAuthMiddleware

        async def health(request):
            return JSONResponse({"status": "ok"})

        async def mutate(request):
            return JSONResponse({"status": "mutated"})

        app = Starlette(
            routes=[
                Route("/api/health", health),
                Route("/api/settings", mutate, methods=["POST", "OPTIONS"]),
            ]
        )
        app.add_middleware(LocalAuthMiddleware)
        return app

    def test_health_is_public_without_key(self):
        from starlette.testclient import TestClient

        with patch("silex.api.server.gateway_auth_required", return_value=True):
            client = TestClient(self._build_app())
            resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_mutating_route_rejected_without_key(self):
        from starlette.testclient import TestClient

        with (
            patch("silex.api.server.gateway_auth_required", return_value=True),
            patch(
                "silex.api.server.RuntimeSettingsStore.ensure_web_api_key",
                return_value="the-real-key",
            ),
        ):
            client = TestClient(self._build_app())
            resp = client.post("/api/settings")

        assert resp.status_code == 401

    def test_mutating_route_rejected_with_wrong_key(self):
        from starlette.testclient import TestClient

        with (
            patch("silex.api.server.gateway_auth_required", return_value=True),
            patch(
                "silex.api.server.RuntimeSettingsStore.ensure_web_api_key",
                return_value="the-real-key",
            ),
        ):
            client = TestClient(self._build_app())
            resp = client.post(
                "/api/settings", headers={"X-Kinthic-Api-Key": "totally-wrong"}
            )

        assert resp.status_code == 401

    def test_mutating_route_allowed_with_correct_key(self):
        from starlette.testclient import TestClient

        with (
            patch("silex.api.server.gateway_auth_required", return_value=True),
            patch(
                "silex.api.server.RuntimeSettingsStore.ensure_web_api_key",
                return_value="the-real-key",
            ),
        ):
            client = TestClient(self._build_app())
            resp = client.post(
                "/api/settings", headers={"X-Kinthic-Api-Key": "the-real-key"}
            )

        assert resp.status_code == 200

    def test_options_preflight_always_allowed(self):
        """CORS preflight (OPTIONS) must never be blocked by the key check,
        or the browser's actual request would never even be attempted."""
        from starlette.testclient import TestClient

        with patch("silex.api.server.gateway_auth_required", return_value=True):
            client = TestClient(self._build_app())
            resp = client.options("/api/settings")

        assert resp.status_code != 401


# ── A2: Host-fallback execution hardening ──────────────────────────────────


class TestHostFallbackHardening:
    """Prove that the reduced-isolation host fallback scrubs secrets from the
    environment and excludes interpreters/package managers from its allowlist."""

    def test_interpreters_and_package_managers_excluded_from_host_allowlist(self):
        from silex.tools.system import _HOST_FALLBACK_ALLOWED_COMMANDS

        dangerous = {"python", "python3", "pip", "npm", "node", "git", "bash", "sh", "uv"}
        assert not (dangerous & _HOST_FALLBACK_ALLOWED_COMMANDS), (
            f"Host fallback allowlist must not include: "
            f"{dangerous & _HOST_FALLBACK_ALLOWED_COMMANDS}"
        )

    @pytest.mark.asyncio
    async def test_host_fallback_scrubs_secret_env_vars(self, tmp_path, monkeypatch):
        """A secret in the daemon's environment must never reach the
        host-fallback subprocess's environment."""
        from silex.tools.system import RunTerminalCommandTool

        monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-leak-me-not")
        monkeypatch.setenv("PATH", "/usr/bin")

        tool = RunTerminalCommandTool()
        tool.client = None  # force host-fallback branch
        tool._workspace_dir = tmp_path

        captured_env = {}

        async def fake_ensure_venv():
            return tmp_path / ".venv"

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return b"", b""

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return FakeProc()

        with (
            patch("silex.tools.system.terminal_execution_enabled", return_value=True),
            patch("silex.tools.system.terminal_host_fallback_enabled", return_value=True),
            patch.object(tool, "_ensure_venv", fake_ensure_venv),
            patch("asyncio.create_subprocess_exec", fake_create_subprocess_exec),
        ):
            result = await tool.execute("echo hello")

        assert "OPENAI_API_KEY" not in captured_env, (
            "Secret leaked into host-fallback subprocess environment!"
        )
        assert "Exit Code: 0" in result

    def test_fail_closed_without_docker_or_opt_in(self):
        """Without Docker and without the explicit opt-in, execution refuses
        even for an otherwise-safe command."""
        from silex.tools.system import RunTerminalCommandTool

        tool = RunTerminalCommandTool()
        tool.client = None

        with (
            patch("silex.tools.system.terminal_execution_enabled", return_value=True),
            patch("silex.tools.system.terminal_host_fallback_enabled", return_value=False),
        ):
            result = asyncio.run(tool.execute("echo hello"))

        assert "blocked" in result.lower()

    def test_dangerous_command_rejected_regardless_of_docker_availability(self):
        """Safety-allowlist rejection must happen before the Docker-availability
        check, so a dangerous command is always explicitly rejected rather than
        surfacing a generic 'Docker unavailable' message."""
        from silex.tools.system import RunTerminalCommandTool

        tool = RunTerminalCommandTool()
        tool.client = None

        with (
            patch("silex.tools.system.terminal_execution_enabled", return_value=True),
            patch("silex.tools.system.terminal_host_fallback_enabled", return_value=False),
        ):
            result = asyncio.run(tool.execute("rm -rf /"))

        assert "rejected" in result.lower()


# ── A3/A5: Crash-injection — dual-write atomicity ──────────────────────────


class TestCrashInjection:
    """Prove that a ChromaDB failure right after a SQLite commit does not
    lose the memory, does not raise past the caller, and is healed by
    reconcile_vector_index()."""

    @pytest.mark.asyncio
    async def test_vector_failure_after_commit_does_not_lose_row(self, tmp_path):
        db, store = await _make_memory_store(tmp_path)
        try:
            store.vs.fail_next_add = True
            memory = await store.add_manual("Crash injection test content one")

            assert memory is not None, "SQLite write must succeed even if the vector write fails"
            row = await db.fetch_one("SELECT * FROM memories WHERE id = ?", (memory.id,))
            assert row is not None, "Memory must be durably persisted in SQLite despite the Chroma crash"

            # The vector store has no entry yet (the simulated crash prevented it).
            assert memory.id not in store.vs._docs

            # Reconciliation must forward-heal the missing vector.
            healed = await store.reconcile_vector_index()
            assert healed == 1
            assert memory.id in store.vs._docs
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_reconcile_purges_orphan_vectors(self, tmp_path):
        """A vector with no backing SQLite row (e.g. left by a crash between
        the vector write and a since-rolled-back SQLite commit) must be
        purged, or it would permanently block re-admission of that content
        via the ChromaDB-only dedup/novelty checks."""
        db, store = await _make_memory_store(tmp_path)
        try:
            store.vs.add_chunks(["orphaned content"], [{"type": "fact"}], ids=["orphan-1"])
            assert "orphan-1" in store.vs._docs

            healed = await store.reconcile_vector_index()
            assert healed == 0
            assert "orphan-1" not in store.vs._docs, "Orphan vector must be purged"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_vector_drift_count_reflects_state(self, tmp_path):
        db, store = await _make_memory_store(tmp_path)
        try:
            assert await store.get_vector_drift_count() == 0

            store.vs.fail_next_add = True
            await store.add_manual("Drift detection test content two")
            assert await store.get_vector_drift_count() == 1

            await store.reconcile_vector_index()
            assert await store.get_vector_drift_count() == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_delete_vector_failure_is_queued_for_retry(self, tmp_path):
        db, store = await _make_memory_store(tmp_path)
        try:
            memory = await store.add_manual("Delete retry queue test content")
            assert memory is not None

            def failing_delete(ids):
                # delete_by_ids is invoked via asyncio.to_thread, i.e. as a
                # plain sync callable — not an awaitable.
                raise RuntimeError("simulated delete failure")

            with patch.object(store.vs, "delete_by_ids", side_effect=failing_delete):
                ok = await store.delete(memory.id)
            assert ok is True

            pending = await db.fetch_all("SELECT * FROM pending_vector_deletes")
            assert len(pending) == 1
            assert pending[0]["memory_id"] == memory.id

            retried = await store.retry_pending_vector_deletes()
            assert retried == 1

            pending_after = await db.fetch_all("SELECT * FROM pending_vector_deletes")
            assert len(pending_after) == 0
        finally:
            await db.close()


# ── B6/B7/C13: Concurrency & write-queue backpressure ──────────────────────


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_parallel_writes_do_not_lock_or_lose_data(self, tmp_path):
        """Many concurrent add_manual calls through the single-writer queue
        must all land, with no 'database is locked' errors."""
        db, store = await _make_memory_store(tmp_path)
        try:
            n = 25
            results = await asyncio.gather(
                *[store.add_manual(f"Concurrency test memory number {i}") for i in range(n)],
                return_exceptions=True,
            )
            errors = [r for r in results if isinstance(r, Exception)]
            assert not errors, f"Unexpected errors under concurrent writes: {errors}"
            assert all(r is not None for r in results)

            count_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM memories")
            assert count_row["cnt"] == n
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_write_queue_sheds_when_saturated(self, tmp_path):
        """When the write queue stays full past the enqueue timeout, a write
        must be rejected (shed) quickly instead of hanging forever."""
        from silex.storage.database import Database

        db = Database(str(tmp_path / "shed.db"))
        db.write_queue = asyncio.Queue(maxsize=1)
        db.WRITE_QUEUE_ENQUEUE_TIMEOUT = 0.2

        # Fill the queue so any further put() would normally block forever.
        await db.write_queue.put(("SELECT 1", (), asyncio.get_event_loop().create_future()))

        loop = asyncio.get_event_loop()
        start = loop.time()
        with pytest.raises(RuntimeError, match="saturated"):
            await db._enqueue_write(("SELECT 2", (), loop.create_future()))
        elapsed = loop.time() - start

        assert elapsed < 2.0, "Shedding must fail fast, not hang indefinitely"

    @pytest.mark.asyncio
    async def test_dead_writer_fails_fast_instead_of_hanging(self, tmp_path):
        """Once the writer loop is marked dead, new writes must raise
        immediately rather than being queued with nothing left to consume them."""
        from silex.storage.database import Database

        db = Database(str(tmp_path / "dead_writer.db"))
        await db.connect()
        try:
            db._writer_dead = True
            with pytest.raises(RuntimeError, match="dead"):
                await db.execute("INSERT INTO goals (id, description, status, priority, created_at, updated_at) VALUES ('x','d','pending','high','t','t')")
        finally:
            db._writer_dead = False
            await db.close()


# ── C13: WAL checkpoint loop ────────────────────────────────────────────────


class TestWalCheckpoint:
    @pytest.mark.asyncio
    async def test_periodic_checkpoint_executes_pragma(self, tmp_path, caplog):
        import logging
        from silex.storage.database import Database

        db = Database(str(tmp_path / "wal_checkpoint.db"))
        db.WAL_CHECKPOINT_INTERVAL_SECONDS = 0.05
        await db.connect()
        try:
            await db.execute(
                "INSERT INTO goals (id, description, status, priority, created_at, updated_at) "
                "VALUES ('wal1','d','pending','high','t','t')"
            )
            with caplog.at_level(logging.DEBUG, logger="silex.storage"):
                await asyncio.sleep(0.4)
            assert any("WAL checkpoint" in rec.message for rec in caplog.records), (
                "Expected at least one periodic WAL checkpoint attempt log line"
            )
        finally:
            await db.close()


# ── A4: Corrupt-row resilience ──────────────────────────────────────────────


class TestCorruptRowResilience:
    @pytest.mark.asyncio
    async def test_bad_json_columns_degrade_gracefully_not_fatal(self, tmp_path):
        """Malformed JSON in tags/child_memory_ids/related_memories must not
        raise — _safe_json_loads falls back to a safe default and the row is
        still returned (degraded, not dropped)."""
        db, store = await _make_memory_store(tmp_path)
        try:
            good = await store.add_manual("A perfectly healthy memory row")
            assert good is not None

            await db.execute(
                """
                INSERT INTO memories (id, content, source, memory_type, importance,
                                      confidence, created_at, last_accessed,
                                      access_count, tags, level, child_memory_ids,
                                      provenance_json, related_memories, archived_at)
                VALUES (?, ?, 'user', 'semantic', 0.5, 0.5, ?, ?, 0, ?, 1, ?, '{}', ?, NULL)
                """,
                (
                    "corrupt-json-row",
                    "A memory row with deliberately corrupted JSON columns",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    "{not valid json",
                    "{also not valid",
                    "[unterminated",
                ),
            )

            # Must not raise despite the malformed JSON columns.
            memories = await store.all_memories()
            ids = {m.id for m in memories}
            assert good.id in ids
            assert "corrupt-json-row" in ids, "Row with recoverable bad JSON should still be returned"

            corrupt = next(m for m in memories if m.id == "corrupt-json-row")
            assert corrupt.tags == [], "Bad JSON must fall back to the safe default, not raise"
            assert corrupt.child_memory_ids == []
            assert corrupt.related_memories == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_invalid_enum_row_is_skipped_not_fatal(self, tmp_path):
        """A row with a value that fails Memory model validation (e.g. an
        unrecognized memory_type) must be skipped, not crash the whole batch."""
        db, store = await _make_memory_store(tmp_path)
        try:
            good = await store.add_manual("Another perfectly healthy memory row")
            assert good is not None

            await db.execute(
                """
                INSERT INTO memories (id, content, source, memory_type, importance,
                                      confidence, created_at, last_accessed,
                                      access_count, tags, level, child_memory_ids,
                                      provenance_json, related_memories, archived_at)
                VALUES (?, ?, 'user', 'totally-bogus-type', 0.5, 0.5, ?, ?, 0, '[]', 1, '[]', '{}', '[]', NULL)
                """,
                (
                    "corrupt-enum-row",
                    "A memory row with an invalid memory_type enum value",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )

            memories = await store.all_memories()
            ids = {m.id for m in memories}
            assert good.id in ids, "Healthy rows must still be returned"
            assert "corrupt-enum-row" not in ids, "Row that fails model validation must be skipped, not raised"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retrieve_context_survives_corrupt_timestamp_in_semantic_pool(self, tmp_path, caplog):
        """A corrupt created_at timestamp must not raise while the semantic
        pool scores it (it's caught and logged) — retrieval must still
        complete and return the rest of the context."""
        import logging

        db, store = await _make_memory_store(tmp_path)
        try:
            good = await store.add_manual("Retrieval survives corrupt sibling rows test")
            assert good is not None

            await db.execute(
                """
                INSERT INTO memories (id, content, source, memory_type, importance,
                                      confidence, created_at, last_accessed,
                                      access_count, tags, level, child_memory_ids,
                                      provenance_json, related_memories, archived_at)
                VALUES (?, ?, 'user', 'semantic', 0.9, 0.5, ?, ?, 0, '[]', 1, '[]', '{}', '[]', NULL)
                """,
                (
                    "corrupt-timestamp-row",
                    "Another corrupt row but this time only the timestamp is bad",
                    "definitely-not-a-timestamp",
                    "definitely-not-a-timestamp",
                ),
            )

            # Force the semantic pool (which parses created_at) to consider
            # the corrupt row as a hit.
            store.vs.canned_search_results = [
                {"id": "corrupt-timestamp-row", "content": "x", "metadata": {}, "distance": 0.1}
            ]

            with caplog.at_level(logging.WARNING, logger="silex.memory"):
                results = await asyncio.wait_for(store.retrieve_context("test query"), timeout=10.0)

            # Must not raise, and the healthy memory must still come through.
            ids = {m.id for m in results}
            assert good.id in ids

            # The semantic-scoring guard must have caught and logged the bad
            # timestamp rather than letting it propagate as an exception.
            assert any(
                "malformed memory row" in rec.message and "corrupt-timestamp-row" in rec.message
                for rec in caplog.records
            )
        finally:
            await db.close()


# ── C12: Query/context budget enforcement ──────────────────────────────────


class TestQueryAndContextBudgets:
    @pytest.mark.asyncio
    async def test_oversized_query_is_truncated_not_rejected(self, tmp_path):
        db, store = await _make_memory_store(tmp_path)
        try:
            from silex.utils.config import MAX_RETRIEVAL_QUERY_CHARS

            huge_query = "word " * (MAX_RETRIEVAL_QUERY_CHARS)  # far bigger than the cap
            # Must not raise / hang despite the pathologically long query.
            results = await asyncio.wait_for(store.retrieve_context(huge_query), timeout=10.0)
            assert isinstance(results, list)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_context_result_respects_char_budget(self, tmp_path):
        from silex.utils.config import MAX_CONTEXT_MEMORY_CHARS

        db, store = await _make_memory_store(tmp_path)
        try:
            # Each memory content is capped at 1000 chars by the schema, so
            # create enough distinct large memories to exceed the budget.
            n_needed = (MAX_CONTEXT_MEMORY_CHARS // 900) + 3
            for i in range(n_needed):
                content = f"Budget test memory {i} " + ("x" * 850)
                mem = await store.add_manual(content, importance=0.9)
                assert mem is not None

            results = await store.retrieve_context("budget test memory")
            total_chars = sum(len(m.content) for m in results)
            # At least one memory must always be returned even if it alone
            # exceeds the budget, but the total shouldn't run away unbounded.
            assert total_chars <= MAX_CONTEXT_MEMORY_CHARS + 1000
        finally:
            await db.close()
