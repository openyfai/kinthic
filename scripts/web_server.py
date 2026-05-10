"""
ARIA Knowledge Graph Visualizer — Web Server.

Security: binds to loopback by default, requires an API key for non-loopback
hosts, uses a WebSocket auth handshake, and exposes local onboarding/settings
APIs for the desktop experience.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aria
from aria.core.cognitive_loop import CognitiveLoop
from aria.utils.dashboard_static import resolve_dashboard_dir
from aria.utils.config import (
    background_actions_enabled,
    get_web_allowed_origins,
    get_web_api_key,
    get_web_host,
    get_web_port,
)

_cognitive_loop: CognitiveLoop | None = None
_db = None
_kg = None
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_WS_MESSAGE_CHARS = int(os.getenv("ARIA_WS_MAX_MESSAGE_CHARS", "2000000"))
_MAX_IMAGE_COUNT = int(os.getenv("ARIA_WS_MAX_IMAGE_COUNT", "4"))
_MAX_TOTAL_IMAGE_BYTES = int(os.getenv("ARIA_WS_MAX_TOTAL_IMAGE_BYTES", str(10 * 1024 * 1024)))
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_WEB_HOST = get_web_host()
_ALLOWED_ORIGINS = get_web_allowed_origins()
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG_ARIA_ROOT = Path(aria.__file__).resolve().parent
_RESOLVED_WEB_UI = resolve_dashboard_dir(
    packaged_aria_pkg=_PKG_ARIA_ROOT,
    repo_root_from_scripts=Path(__file__).resolve().parent.parent,
)
_WEB_UI_OUT = str(_RESOLVED_WEB_UI) if _RESOLVED_WEB_UI else ""
_WEB_UI_PACKAGED = bool(_RESOLVED_WEB_UI)


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._events[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


_rest_limiter = RateLimiter(limit=120, window_seconds=60)
_ws_limiter = RateLimiter(limit=40, window_seconds=60)


def _is_loopback_host(host: str) -> bool:
    return host.split(":", 1)[0].lower() in _LOOPBACK_HOSTS


def _current_api_key() -> str:
    return get_web_api_key()


def _auth_required() -> bool:
    return not _is_loopback_host(_WEB_HOST) or bool(_current_api_key())


def _is_authorized(authorization: str | None = None, token: str | None = None) -> bool:
    api_key = _current_api_key()
    if not api_key:
        return _is_loopback_host(_WEB_HOST)
    return authorization == f"Bearer {api_key}" or token == api_key


def _check_rate_limit(key: str) -> None:
    if not _rest_limiter.check(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")


def _check_auth(authorization: str | None = None, token: str | None = None, rate_key: str = "rest") -> None:
    _check_rate_limit(rate_key)
    if _auth_required() and not _is_authorized(authorization, token):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _sanitize_turn(turn) -> dict[str, Any]:
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


async def background_loop():
    while True:
        await asyncio.sleep(900)
        if background_actions_enabled() and _cognitive_loop:
            await _cognitive_loop.tick()

async def proactive_telegram_loop():
    import random
    from aria.runtime.settings import RuntimeSettingsStore
    store = RuntimeSettingsStore()
    
    while True:
        # Check every 2-6 hours randomly to simulate organic thought pattern
        delay = random.randint(7200, 21600)
        await asyncio.sleep(delay)
        
        if background_actions_enabled() and _cognitive_loop:
            settings = store.load_settings()
            paired_users = settings.get("telegram", {}).get("paired_users", [])
            
            if not paired_users:
                continue
                
            bot_token = settings.get("telegram_token") or os.getenv("TELEGRAM_BOT_TOKEN")
            
            if bot_token and paired_users:
                # Randomly pick a paired user to message
                user_id = random.choice(paired_users)["user_id"]
                
                # Have the loop generate a proactive message
                try:
                    result = await _cognitive_loop.process(
                        "System background directive: Proactively reflect on our last conversations and send an unprompted message to the user with a hypothesis, question, or thought you formed while they were away. Be completely in character. Make it brief."
                    )
                    from telegram import Bot
                    bot = Bot(token=bot_token)
                    await bot.send_message(chat_id=user_id, text=result.response, parse_mode="Markdown")
                except Exception as e:
                    log.warning("Proactive Telegram message failed: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cognitive_loop, _db, _kg
    if not _is_loopback_host(_WEB_HOST) and not _current_api_key():
        raise RuntimeError(
            "ARIA_WEB_API_KEY must be set before binding the web server beyond loopback."
        )
    _cognitive_loop = CognitiveLoop()
    await _cognitive_loop.startup()
    _db = _cognitive_loop.db
    _kg = _cognitive_loop.kg
    bg_task = asyncio.create_task(background_loop())
    proactive_task = asyncio.create_task(proactive_telegram_loop())
    yield
    bg_task.cancel()
    proactive_task.cancel()
    if _cognitive_loop:
        await _cognitive_loop.shutdown()


app = FastAPI(title="ARIA Web UI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS or ["http://127.0.0.1:8000"],
    allow_credentials="*" not in _ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def _request_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/api/bootstrap")
async def bootstrap_state(request: Request):
    _check_rate_limit(f"bootstrap:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return {
        "auth_required": _auth_required(),
        "has_local_api_key": bool(_current_api_key()),
        "ui_packaged": _WEB_UI_PACKAGED,
        "setup": await _cognitive_loop.get_setup_status(),
        "providers": await _cognitive_loop.list_supported_providers(),
    }


@app.get("/api/setup/status")
async def setup_status(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"setup-status:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.get_setup_status()


@app.get("/api/providers")
async def get_providers(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"providers:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.list_supported_providers()


@app.get("/api/settings")
async def get_settings(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"settings:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.get_runtime_settings()


@app.post("/api/setup")
async def complete_setup(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization, rate_key=f"setup-save:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    payload = {**payload, "setup_completed": True}
    
    # Handle Telegram Pairing Code provided by UI
    telegram_pairing_code = payload.pop("telegram_pairing_code", None)
    if telegram_pairing_code:
        store = _cognitive_loop.context_builder.settings_store
        settings = store.load_settings()
        from datetime import datetime, timezone, timedelta
        pair_codes = list(settings.get("telegram", {}).get("pair_codes", []))
        pair_codes.append({
            "code": telegram_pairing_code.strip().upper(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(), # Long expiration for setup
            "consumed_at": None,
            "paired_user_id": None,
        })
        settings.setdefault("telegram", {})["pair_codes"] = pair_codes
        store.save_settings(settings)
        
    saved = await _cognitive_loop.update_runtime_settings(payload)
    return {"ok": True, "settings": saved, "status": await _cognitive_loop.get_setup_status()}


@app.post("/api/setup/test-provider")
async def test_provider_connection(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization, rate_key=f"setup-test:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    provider = str(payload.get("provider", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    model = str(payload.get("model", "")).strip() or None
    known = {entry["id"] for entry in await _cognitive_loop.list_supported_providers()}
    if provider not in known:
        raise HTTPException(status_code=400, detail="Unknown provider.")
    return await _cognitive_loop.test_provider_credentials(provider=provider, api_key=api_key, model=model)


@app.post("/api/settings")
async def update_settings(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization, rate_key=f"settings-save:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    saved = await _cognitive_loop.update_runtime_settings(payload)
    return {"ok": True, "settings": saved}


@app.get("/api/usage")
async def get_usage(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"usage:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.get_usage_summary()


@app.get("/api/telegram/users")
async def get_telegram_users(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"telegram-users:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return _cognitive_loop.settings_store.list_telegram_users()


@app.post("/api/telegram/pair-code")
async def create_pair_code(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"telegram-pair:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    code = _cognitive_loop.settings_store.create_pair_code()
    return {"code": code}


@app.get("/api/sessions")
async def get_sessions(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"sessions:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    sessions = await _cognitive_loop.session.get_all_sessions()
    return [{"id": s.id, "started_at": s.started_at, "turn_count": s.turn_count, "topics": s.topics} for s in sessions]


@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id: str, request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"session:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    turns = await _cognitive_loop.session.get_turns_for_session(session_id)
    return [_sanitize_turn(t) for t in turns]


@app.post("/api/sessions/new")
async def create_new_session(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"session-new:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    await _cognitive_loop.session.end_session()
    new_session = await _cognitive_loop.session.start_session()
    return {"id": new_session.id}


@app.get("/api/goals")
async def get_goals(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"goals:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    goals = await _cognitive_loop.goals.get_active()
    return [{"id": g.id, "description": g.description, "priority": g.priority.value, "created_at": g.created_at} for g in goals]


@app.get("/api/health")
async def get_health(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"health:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.get_health_status()


@app.get("/api/tool-approvals")
async def get_tool_approvals(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"approvals:{_request_key(request)}")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    return await _cognitive_loop.tool_registry.get_pending_approvals()


@app.post("/api/tool-approvals/{approval_id}/{decision}")
async def resolve_tool_approval(approval_id: str, decision: str, request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"approval-resolve:{_request_key(request)}")
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected.")
    if not _cognitive_loop:
        raise HTTPException(status_code=503, detail="System booting")
    ok = await _cognitive_loop.tool_registry.resolve_approval(approval_id, decision)
    return {"ok": ok}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    client_key = websocket.client.host if websocket.client else "unknown"
    if not _ws_limiter.check(client_key):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    if not _cognitive_loop:
        await websocket.close(code=1011)
        return

    if _auth_required():
        try:
            auth_payload = json.loads(await websocket.receive_text())
        except Exception:
            await websocket.close(code=1008)
            return
        token = auth_payload.get("api_key") if isinstance(auth_payload, dict) else None
        if auth_payload.get("type") != "auth" or not _is_authorized(token=token):
            await websocket.close(code=1008)
            return
        await websocket.send_json({"type": "auth_ok"})
    else:
        await websocket.send_json({"type": "auth_ok"})

    loop = asyncio.get_running_loop()
    stop_flag = {"stopped": False}

    def status_callback(msg: str):
        clean_msg = re.sub(r"\[.*?\]", "", msg).strip()
        if clean_msg:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "monologue", "text": clean_msg}),
                loop,
            )

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > _MAX_WS_MESSAGE_CHARS:
                await websocket.send_json({"type": "error", "text": "Message payload is too large.", "error_kind": "model_error"})
                continue

            user_text = data
            images = None
            payload = None
            try:
                payload = json.loads(data)
                if isinstance(payload, dict):
                    if payload.get("type") == "auth":
                        continue
                    user_text = payload.get("text", "")
                    if payload.get("stop") is True:
                        user_text = "__STOP__"
                    if "images" in payload:
                        images = _decode_images(payload)
            except json.JSONDecodeError:
                pass
            except ValueError as exc:
                await websocket.send_json({"type": "error", "text": str(exc), "error_kind": "model_error"})
                continue

            if user_text == "__STOP__":
                stop_flag["stopped"] = True
                continue

            stop_flag["stopped"] = False
            try:
                if isinstance(payload, dict):
                    req_session_id = payload.get("session_id")
                    if req_session_id and (_cognitive_loop.session.current is None or _cognitive_loop.session.current.id != req_session_id):
                        await _cognitive_loop.session.resume_specific(req_session_id)

                response = await _cognitive_loop.process(user_text, status_callback=status_callback, images=images)
                full_text = response.response
                await websocket.send_json({"type": "response_start"})

                words = full_text.split(" ")
                buffer = ""
                for i, word in enumerate(words):
                    if stop_flag["stopped"]:
                        break
                    buffer += word + (" " if i < len(words) - 1 else "")
                    if (i + 1) % 3 == 0 or i == len(words) - 1:
                        await websocket.send_json({"type": "response_chunk", "text": buffer})
                        buffer = ""
                        await asyncio.sleep(0.02)

                await websocket.send_json(
                    {
                        "type": "response_done",
                        "confidence": round(response.confidence * 100),
                        "graph_nodes_added": len(response.causal_observations),
                        "goals_updated": len(response.goal_updates),
                    }
                )
            except Exception as exc:
                detail = str(exc)
                low = detail.lower()
                if "api" in low and ("key" in low or "401" in detail or "403" in detail):
                    user_msg = (
                        "The model provider rejected this request. Check your API key and quota in Settings "
                        "or run `aria doctor --ping` from a terminal on this machine."
                    )
                elif "429" in detail or ("rate" in low and "limit" in low):
                    user_msg = "Provider rate limit hit — wait a moment and try again, or switch model/provider."
                elif "quota" in low or "billing" in low or "exhausted" in low:
                    user_msg = "Provider quota or billing limit — verify your account in the provider dashboard."
                elif "timeout" in low or "timed out" in low:
                    user_msg = "The request timed out — try a shorter prompt, a faster model, or check local Ollama is running."
                elif "model" in low and ("not found" in low or "does not exist" in low):
                    user_msg = "That model name was not found — pick another model under Settings or `aria models`."
                else:
                    user_msg = "Generation failed. Check the ARIA server logs for details or run `aria doctor --ping`."
                await websocket.send_json({"type": "error", "text": user_msg, "error_kind": "model_error"})
    except WebSocketDisconnect:
        return


@app.get("/api/graph")
async def get_graph_data(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization, rate_key=f"graph:{_request_key(request)}")
    if not _kg:
        raise HTTPException(status_code=503, detail="Knowledge graph not loaded.")

    nodes = []
    edges = []
    for node_id, data in _kg.graph.nodes(data=True):
        nodes.append(
            {
                "id": node_id,
                "label": data.get("content", ""),
                "group": data.get("node_type", "fact"),
                "val": data.get("confidence", 0.5) * 10,
            }
        )

    for u, v, data in _kg.graph.edges(data=True):
        edges.append(
            {
                "source": u,
                "target": v,
                "label": data.get("edge_type", "related"),
                "strength": data.get("strength", 0.5),
            }
        )

    return {"nodes": nodes, "links": edges}


_MISSING_UI_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>ARIA — Dashboard assets missing</title></head>
<body style="font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;line-height:1.5;">
<h1>ARIA API is running</h1>
<p>Official <code>pip install openyfai-aria</code> wheels should include the dashboard. If you installed from PyPI and see this page, try upgrading the package or file an issue.</p>
<p><strong>Developers</strong> (git clone): build the Next.js app so <code>aria-ui/out/index.html</code> exists, then restart <code>aria web</code>:</p>
<pre style="background:#f4f4f5;padding:1rem;">cd aria-ui &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p><strong>Maintainers</strong> publishing wheels: run the release workflow (or copy <code>aria-ui/out</code> into <code>aria/web_dist/</code>) before <code>python -m build</code>. See CONTRIBUTING.md.</p>
<p>REST and WebSocket APIs under <code>/api/*</code> and <code>/ws/chat</code> remain available.</p>
</body></html>"""


if _WEB_UI_PACKAGED:
    app.mount("/", StaticFiles(directory=_WEB_UI_OUT, html=True), name="static")
else:

    @app.get("/", response_class=HTMLResponse)
    async def _ui_not_built_placeholder():
        return HTMLResponse(content=_MISSING_UI_HTML)

    print(
        "WARNING: Dashboard static files not found (aria/web_dist after release build, "
        "or aria-ui/out when developing). Serving `/` help HTML; REST and WebSockets still run."
    )


if __name__ == "__main__":
    host = get_web_host()
    port = get_web_port()
    print(f"Starting ARIA Knowledge Graph Visualizer on http://{host}:{port}")
    if not _current_api_key():
        print("No ARIA web API key configured. This is only allowed on loopback binds.")
    uvicorn.run(app, host=host, port=port)
