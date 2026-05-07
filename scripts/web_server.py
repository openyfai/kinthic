"""
ARIA Knowledge Graph Visualizer — Web Server.

Security: Binds to localhost by default. Optional API key authentication.
Uses a shared DB/KG instance via FastAPI lifespan (not per-request creation).
"""

import os
import sys
import json
import base64
import binascii
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aria.core.cognitive_loop import CognitiveLoop
from aria.utils.config import background_actions_enabled, autonomy_policy_snapshot

# ---------------------------------------------------------------------------
# Shared state (populated during lifespan)
# ---------------------------------------------------------------------------

_cognitive_loop: CognitiveLoop | None = None
_db = None
_kg = None


import asyncio

async def background_loop():
    """Runs continuously in the background, waking ARIA up to act proactively."""
    while True:
        # Sleep for 15 minutes to save API costs
        await asyncio.sleep(900)
        
        # Only run if explicitly enabled to prevent burning API credits
        if background_actions_enabled() and _cognitive_loop:
            await _cognitive_loop.tick()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — create the full CognitiveLoop."""
    global _cognitive_loop, _db, _kg
    _cognitive_loop = CognitiveLoop()
    await _cognitive_loop.startup()
    _db = _cognitive_loop.db
    _kg = _cognitive_loop.kg
    
    # Start ARIA's internal clock for proactive behavior
    bg_task = asyncio.create_task(background_loop())
    
    yield
    
    bg_task.cancel()
    if _cognitive_loop:
        await _cognitive_loop.shutdown()


app = FastAPI(title="ARIA Web UI", lifespan=lifespan)

_WEB_HOST = os.getenv("ARIA_WEB_HOST", "127.0.0.1")
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ARIA_WEB_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS or ["http://127.0.0.1:8000"],
    allow_credentials="*" not in _ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

_API_KEY = os.getenv("ARIA_WEB_API_KEY", "")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_WS_MESSAGE_CHARS = int(os.getenv("ARIA_WS_MAX_MESSAGE_CHARS", "2000000"))
_MAX_IMAGE_COUNT = int(os.getenv("ARIA_WS_MAX_IMAGE_COUNT", "4"))
_MAX_TOTAL_IMAGE_BYTES = int(os.getenv("ARIA_WS_MAX_TOTAL_IMAGE_BYTES", str(10 * 1024 * 1024)))
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _is_loopback_host(host: str) -> bool:
    return host.split(":", 1)[0].lower() in _LOOPBACK_HOSTS


def _is_authorized(authorization: str | None = None, token: str | None = None) -> bool:
    """Validate API key. Localhost-only dev may run without one."""
    if not _API_KEY:
        return _is_loopback_host(_WEB_HOST)
    return authorization == f"Bearer {_API_KEY}" or token == _API_KEY


def _check_auth(authorization: str | None = None, token: str | None = None):
    """Validate API key if one is configured; require one for non-loopback binds."""
    if not _is_authorized(authorization, token):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _sanitize_turn(turn) -> dict:
    """Return only chat transcript fields needed by the UI."""
    return {
        "id": turn.id,
        "session_id": turn.session_id,
        "turn_number": turn.turn_number,
        "user_input": turn.user_input,
        "response": turn.response,
        "confidence": turn.confidence,
        "created_at": turn.created_at,
    }


def _decode_images(payload: dict) -> list[dict] | None:
    raw_images = payload.get("images")
    if not raw_images:
        return None
    if not isinstance(raw_images, list) or len(raw_images) > _MAX_IMAGE_COUNT:
        raise ValueError(f"Too many images. Maximum is {_MAX_IMAGE_COUNT}.")

    images = []
    total_bytes = 0
    for img in raw_images:
        if not isinstance(img, dict):
            raise ValueError("Invalid image payload.")
        mime = img.get("mime")
        data = img.get("data")
        if mime not in _ALLOWED_IMAGE_MIMES or not isinstance(data, str):
            raise ValueError("Unsupported image payload.")
        try:
            img_bytes = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Invalid image encoding.") from None
        total_bytes += len(img_bytes)
        if total_bytes > _MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("Image payload too large.")
        images.append({"mime": mime, "bytes": img_bytes})
    return images


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from fastapi import WebSocket, WebSocketDisconnect
import re

from fastapi.responses import FileResponse

@app.get("/api/sessions")
async def get_sessions(authorization: str | None = Header(default=None)):
    """Get all past chat sessions."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    sessions = await _cognitive_loop.session.get_all_sessions()
    return [{"id": s.id, "started_at": s.started_at, "turn_count": s.turn_count, "topics": s.topics} for s in sessions]

@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id: str, authorization: str | None = Header(default=None)):
    """Get chat history for a specific session."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    turns = await _cognitive_loop.session.get_turns_for_session(session_id)
    return [_sanitize_turn(t) for t in turns]

@app.post("/api/sessions/new")
async def create_new_session(authorization: str | None = Header(default=None)):
    """Start a new session."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    # End current session and start a new one
    await _cognitive_loop.session.end_session()
    new_session = await _cognitive_loop.session.start_session()
    return {"id": new_session.id}

@app.get("/api/goals")
async def get_goals(authorization: str | None = Header(default=None)):
    """Get all active goals."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    goals = await _cognitive_loop.goals.get_active()
    return [{"id": g.id, "description": g.description, "priority": g.priority.value, "created_at": g.created_at} for g in goals]

@app.get("/api/health")
async def get_health(authorization: str | None = Header(default=None)):
    """Report runtime health and active autonomy policy for the operator UI."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.get_health_status()

@app.get("/api/tool-approvals")
async def get_tool_approvals(authorization: str | None = Header(default=None)):
    """List pending tool approvals for operator review."""
    _check_auth(authorization)
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.tool_registry.get_pending_approvals()

@app.post("/api/tool-approvals/{approval_id}/{decision}")
async def resolve_tool_approval(approval_id: str, decision: str, authorization: str | None = Header(default=None)):
    """Approve or reject a pending tool request."""
    _check_auth(authorization)
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected.")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    ok = await _cognitive_loop.tool_registry.resolve_approval(approval_id, decision)
    return {"ok": ok}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat and internal monologue streaming."""
    token = websocket.query_params.get("token")
    if not _is_authorized(token=token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    if not _cognitive_loop:
        await websocket.close(code=1011)
        return

    loop = asyncio.get_running_loop()
    stop_flag = {"stopped": False}

    def status_callback(msg: str):
        # Strip rich formatting tags (e.g. [magenta]) from the console output
        clean_msg = re.sub(r'\[.*?\]', '', msg).strip()
        if clean_msg:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "monologue", "text": clean_msg}),
                loop
            )

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > _MAX_WS_MESSAGE_CHARS:
                await websocket.send_json({
                    "type": "error",
                    "text": "Message payload is too large.",
                    "error_kind": "model_error"
                })
                continue
            
            user_text = data
            images = None
            payload = None

            try:
                payload = json.loads(data)
                if isinstance(payload, dict):
                    user_text = payload.get("text", "")
                    if payload.get("stop") is True:
                        user_text = "__STOP__"
                    
                    if "images" in payload:
                        images = _decode_images(payload)
            except json.JSONDecodeError:
                pass  # Fallback to raw text
            except ValueError as e:
                await websocket.send_json({
                    "type": "error",
                    "text": str(e),
                    "error_kind": "model_error"
                })
                continue

            # Handle stop signal
            if user_text == "__STOP__":
                stop_flag["stopped"] = True
                continue

            stop_flag["stopped"] = False

            try:
                # If the UI sent a specific session ID, switch to it
                if isinstance(payload, dict):
                    req_session_id = payload.get("session_id")
                    if req_session_id and (_cognitive_loop.session.current is None or _cognitive_loop.session.current.id != req_session_id):
                        await _cognitive_loop.session.resume_specific(req_session_id)

                # Process the message through ARIA (thinking dots stay visible during this)
                response = await _cognitive_loop.process(user_text, status_callback=status_callback, images=images)
                full_text = response.response

                # NOW signal that streaming has started (after processing is done)
                await websocket.send_json({"type": "response_start"})

                # Stream the response in chunks (word-by-word for natural feel)
                words = full_text.split(' ')
                buffer = ""
                for i, word in enumerate(words):
                    if stop_flag["stopped"]:
                        break
                    buffer += word + (' ' if i < len(words) - 1 else '')
                    # Send every 3 words as a chunk for efficiency
                    if (i + 1) % 3 == 0 or i == len(words) - 1:
                        await websocket.send_json({
                            "type": "response_chunk",
                            "text": buffer
                        })
                        buffer = ""
                        await asyncio.sleep(0.02)  # ~50 words/sec streaming speed

                # Send completion signal with metadata
                await websocket.send_json({
                    "type": "response_done",
                    "confidence": round(response.confidence * 100),
                    "graph_nodes_added": len(response.causal_observations),
                    "goals_updated": len(response.goal_updates)
                })

            except Exception as e:
                print(f"WebSocket processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "text": "Internal error while generating a response.",
                    "error_kind": "model_error"
                })

    except WebSocketDisconnect:
        print("WebSocket client disconnected.")



@app.get("/api/graph")
async def get_graph_data(authorization: str | None = Header(default=None)):
    """Returns the nodes and edges from the knowledge graph."""
    _check_auth(authorization)

    if not _kg:
        raise HTTPException(status_code=503, detail="Knowledge graph not loaded.")

    nodes = []
    edges = []

    for node_id, data in _kg.graph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "label": data.get("content", ""),
            "group": data.get("node_type", "fact"),
            "val": data.get("confidence", 0.5) * 10
        })

    for u, v, data in _kg.graph.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "label": data.get("edge_type", "related"),
            "strength": data.get("strength", 0.5)
        })

    return {
        "nodes": nodes,
        "links": edges
    }

from fastapi.staticfiles import StaticFiles

# Mount the Next.js static export. Must be placed after all other routes so it doesn't override /api or /ws.
out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aria-ui", "out")
if os.path.exists(out_dir):
    app.mount("/", StaticFiles(directory=out_dir, html=True), name="static")
else:
    print("⚠️ WARNING: aria-ui/out directory not found. Web UI will not be served. Run 'npm run build' in aria-ui/.")

if __name__ == "__main__":
    host = os.getenv("ARIA_WEB_HOST", "127.0.0.1")  # Localhost by default
    port = int(os.getenv("ARIA_WEB_PORT", "8000"))
    print(f"🚀 Starting ARIA Knowledge Graph Visualizer on http://{host}:{port}")
    if not _API_KEY:
        print("ℹ️  No ARIA_WEB_API_KEY set — running without authentication (localhost only).")
    uvicorn.run(app, host=host, port=port)
