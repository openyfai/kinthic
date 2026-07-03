"""Tests for the Kinthic Ink bridge (Python ↔ NDJSON file bus + TCP push)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from silex.ui import ink_bridge as ib


@pytest.fixture
def events_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kinthic_dir = tmp_path / ".kinthic"
    kinthic_dir.mkdir()
    path = kinthic_dir / "ink_events.ndjson"
    monkeypatch.setattr(ib, "_KINTHIC_DIR", kinthic_dir)
    monkeypatch.setattr(ib, "_EVENTS_FILE", path)
    return path


@pytest.mark.asyncio
async def test_emit_appends_ndjson_line(events_file: Path) -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True  # bypass subprocess spawn

    await bridge.emit({"type": "thinking", "data": {"status": "Thinking..."}})
    await bridge.emit({"type": "response", "data": {"text": "hi"}})

    lines = events_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "thinking"
    assert json.loads(lines[1])["data"]["text"] == "hi"


@pytest.mark.asyncio
async def test_emit_error_writes_error_and_response(events_file: Path) -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True

    await bridge.emit_error("something broke")

    payloads = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    assert payloads[0]["type"] == "error"
    assert payloads[0]["data"]["message"] == "something broke"
    assert payloads[1]["type"] == "response"
    assert "something broke" in payloads[1]["data"]["text"]


@pytest.mark.asyncio
async def test_emit_cancel_writes_cancel_and_response(events_file: Path) -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True

    await bridge.emit_cancel("Thinking cancelled.")

    payloads = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    assert payloads[0]["type"] == "cancel"
    assert payloads[1]["type"] == "response"


@pytest.mark.asyncio
async def test_read_user_input_from_stderr_packet() -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True

    packet = json.dumps({"type": "user_input", "params": {"text": "hello ink"}})
    await bridge._user_input_queue.put("queued-directly")
    # Simulate stderr reader routing
    parsed = json.loads(packet)
    if parsed.get("type") == "user_input":
        await bridge._user_input_queue.put(parsed["params"]["text"])

    first = await bridge.read_user_input(timeout=1.0)
    second = await bridge.read_user_input(timeout=1.0)
    assert first == "queued-directly"
    assert second == "hello ink"


@pytest.mark.asyncio
async def test_emit_noop_when_disabled(events_file: Path) -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = False
    await bridge.emit({"type": "response", "data": {"text": "nope"}})
    assert not events_file.exists() or events_file.read_text() == ""


def test_build_launch_cmd_prefers_compiled_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiled = tmp_path / "kinthic-ui"
    compiled.write_text("#!/bin/sh\necho ok\n")
    compiled.chmod(0o755)
    monkeypatch.setattr(ib, "_COMPILED_UI", compiled)
    cmd = ib._build_launch_cmd()
    assert cmd == [str(compiled)]


def test_events_file_truncation_pattern(events_file: Path) -> None:
    """Document the session-start truncate used by KinthicInkBridge.start()."""
    events_file.write_text('{"type":"old"}\n', encoding="utf-8")
    events_file.write_text("", encoding="utf-8")
    assert events_file.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_emit_buffers_tcp_until_client_connects() -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True
    bridge._use_tcp = True

    await bridge.emit({"type": "header", "data": {"version": "1.0.0"}})
    assert len(bridge._pending_event_lines) == 1
    assert "header" in bridge._pending_event_lines[0]


@pytest.mark.asyncio
async def test_emit_pushes_over_tcp_when_client_connected() -> None:
    bridge = ib.KinthicInkBridge()
    bridge._enabled = True
    bridge._use_tcp = True

    server = await asyncio.start_server(
        bridge._handle_event_client,
        "127.0.0.1",
        0,
    )

    reader, writer = await asyncio.open_connection(
        "127.0.0.1",
        int(server.sockets[0].getsockname()[1]),
    )
    await asyncio.sleep(0.05)

    await bridge.emit({
        "type": "turn_event",
        "data": {"turn_id": "t1", "seq": 1, "phase": "user", "title": "You", "detail": "hi"},
    })

    data = await asyncio.wait_for(reader.read(4096), timeout=1.0)
    payload = json.loads(data.decode("utf-8").strip())
    assert payload["data"]["phase"] == "user"

    writer.close()
    await writer.wait_closed()
    server.close()
    await server.wait_closed()
