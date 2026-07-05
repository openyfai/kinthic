"""Tests for the Silex memory MCP server."""

from __future__ import annotations

import json

import pytest

from silex.mcp.server.audit import McpAuditLog
from silex.mcp.server.lifecycle import McpServerContext, create_standalone_context
from silex.mcp.server.schemas import (
    AdmissionInfo,
    RecallRequest,
    RememberExplicitRequest,
    RememberRequest,
    memory_to_record,
)
from silex.mcp.server import service as svc
from silex.models.schemas import Memory, MemorySource, MemoryType


@pytest.mark.asyncio
async def test_recall_after_explicit_remember(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("SILEX_DB", str(db_path))

    ctx = await create_standalone_context(str(db_path))
    try:
        write = await svc.remember_explicit(
            ctx,
            RememberExplicitRequest(
                content="Staging DB is postgres://staging.internal:5432/kinthic"
            ),
        )
        payload = json.loads(write)
        assert payload["admission"]["accepted"] is True

        recalled = json.loads(
            await svc.recall(ctx, RecallRequest(query="staging postgres URL"))
        )
        assert recalled["count"] >= 1
        assert any("postgres" in m["content"] for m in recalled["memories"])
    finally:
        await ctx.memory.db.close()


@pytest.mark.asyncio
async def test_remember_returns_admission_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("SILEX_DB", str(db_path))

    ctx = await create_standalone_context(str(db_path))
    try:
        result = json.loads(
            await svc.remember(
                ctx,
                RememberRequest(
                    content="User prefers dark mode in all tools", importance=0.9
                ),
            )
        )
        assert "admission" in result
        assert "reason" in result["admission"]
    finally:
        await ctx.memory.db.close()


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess_calls(tmp_path):
    audit = McpAuditLog(path=tmp_path / "audit.ndjson")
    client = "test-client"
    for _ in range(60):
        assert audit.check_rate_limit(client, "silex_recall")
    assert audit.check_rate_limit(client, "silex_recall") is False


def test_memory_to_record_roundtrip():
    mem = Memory(
        content="hello world test",
        source=MemorySource.USER,
        memory_type=MemoryType.SEMANTIC,
    )
    rec = memory_to_record(
        mem, admission=AdmissionInfo(accepted=True, reason="explicit")
    )
    assert rec.memory_id == mem.id
    assert rec.admission.reason == "explicit"


@pytest.mark.asyncio
async def test_concurrent_recall_and_write_no_deadlock(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("SILEX_DB", str(db_path))

    ctx = await create_standalone_context(str(db_path))
    try:
        import asyncio

        async def writer(i: int):
            await svc.remember_explicit(
                ctx,
                RememberExplicitRequest(
                    content=f"Concurrent fact number {i} for testing"
                ),
            )

        async def reader():
            return await svc.recall(ctx, RecallRequest(query="concurrent fact"))

        tasks = [writer(i) for i in range(5)] + [reader() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, errors
    finally:
        await ctx.memory.db.close()


@pytest.mark.asyncio
async def test_auth_middleware_rejects_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("KINTHIC_GATEWAY_AUTH", "1")
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)

    from starlette.responses import Response
    from silex.api.server import LocalAuthMiddleware

    async def app(scope, receive, send):
        resp = Response("ok")
        await resp(scope, receive, send)

    middleware = LocalAuthMiddleware(app)

    scope = {"type": "http", "method": "GET", "path": "/mcp", "headers": []}
    called = {"ok": False}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            assert message["status"] == 401
            called["ok"] = True

    await middleware(scope, receive, send)
    assert called["ok"]


def test_mcp_tool_registration():
    from silex.mcp.server.app import create_mcp_stdio
    from silex.mcp.server.audit import McpAuditLog

    class _Mem:
        vs = type("VS", (), {"is_active": False})()

    class _Kg:
        async def retrieve_relevant_context(self, *a, **k):
            return []

    ctx = McpServerContext(
        memory=_Mem(), kg=_Kg(), client_id="test", audit=McpAuditLog()
    )
    mcp = create_mcp_stdio(ctx)
    assert mcp is not None


@pytest.mark.asyncio
async def test_forget_without_confirm_returns_structured_error(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("SILEX_DB", str(db_path))

    ctx = await create_standalone_context(str(db_path))
    try:
        from silex.mcp.server.schemas import ForgetRequest

        raw = await svc.forget(
            ctx,
            ForgetRequest(
                memory_id="00000000-0000-0000-0000-000000000000", confirm=False
            ),
        )
        payload = json.loads(raw)
        assert payload["code"] == "confirmation_required"
    finally:
        await ctx.memory.db.close()


@pytest.mark.asyncio
async def test_mcp_streamable_http_protocol(tmp_path, monkeypatch):
    """E2E: initialize → tools/list → tools/call over mounted Streamable HTTP."""
    from contextlib import asynccontextmanager

    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.testclient import TestClient

    from silex.mcp.server.app import build_mcp_http, set_mcp_context

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KINTHIC_HOME", str(tmp_path))
    monkeypatch.setenv("SILEX_DB", str(db_path))

    ctx = await create_standalone_context(str(db_path))
    set_mcp_context(ctx)
    mcp = build_mcp_http(ctx)
    inner = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    outer = Starlette(routes=[Mount("/mcp", app=inner)], lifespan=lifespan)
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }

    try:
        with TestClient(outer, base_url="http://127.0.0.1") as client:
            init_resp = client.post("/mcp", json=init_body, headers=headers)
            assert init_resp.status_code == 200, init_resp.text

            session_id = init_resp.headers.get("mcp-session-id", "")
            req_headers = dict(headers)
            if session_id:
                req_headers["Mcp-Session-Id"] = session_id

            tools_resp = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=req_headers,
            )
            assert tools_resp.status_code == 200, tools_resp.text
            assert "silex_recall" in tools_resp.text

            call_resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "silex_remember_explicit",
                        "arguments": {
                            "content": "Protocol E2E fact: pytest validates MCP HTTP mount",
                            "importance": 0.8,
                        },
                    },
                },
                headers=req_headers,
            )
            assert call_resp.status_code == 200, call_resp.text
            assert "accepted" in call_resp.text
    finally:
        await ctx.memory.db.close()
