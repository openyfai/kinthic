import json

import pytest

from agent.compute.sidecar_daemon import handle_client


@pytest.mark.asyncio
async def test_sidecar_rejects_unauthenticated_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("KINTHIC_WORKER_SESSION_KEY", "test-session-secret")

    class MockReader:
        async def read(self):
            return json.dumps({"command": "echo should_fail"}).encode("utf-8")

    class MockWriter:
        def __init__(self):
            self.data = b""

        def write(self, d):
            self.data += d

        async def drain(self):
            pass

        def close(self):
            pass

    writer = MockWriter()
    await handle_client(MockReader(), writer)
    response = json.loads(writer.data.decode("utf-8"))
    assert response["exit_code"] == -1
    assert "session_key" in response.get("error", "").lower()


@pytest.mark.asyncio
async def test_sidecar_execution(tmp_path, monkeypatch):
    """Verify that the sidecar daemon can execute a command with valid session key."""
    session_key = "test-session-secret-for-sidecar"
    monkeypatch.setenv("KINTHIC_WORKER_SESSION_KEY", session_key)

    class MockReader:
        async def read(self):
            return json.dumps(
                {
                    "command": "echo sidecar_test_output",
                    "session_key": session_key,
                }
            ).encode("utf-8")

    class MockWriter:
        def __init__(self):
            self.data = b""

        def write(self, d):
            self.data += d

        async def drain(self):
            pass

        def close(self):
            pass

    reader = MockReader()
    writer = MockWriter()

    await handle_client(reader, writer)

    response = json.loads(writer.data.decode("utf-8"))
    assert response["exit_code"] == 0
    assert "sidecar_test_output" in response["output"]
