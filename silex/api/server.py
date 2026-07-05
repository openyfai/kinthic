from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import hmac
import os
import json
import uuid
import asyncio
import time

from silex.storage.database import Database
from silex.utils.config import (
    KINTHIC_BACKUPS,
    SILEX_DB,
    gateway_allowed_origins,
    gateway_auth_required,
    gateway_host,
    gateway_port,
)
from silex.core.cognitive_loop import CognitiveLoop
from silex.utils.logger import setup_logger
from silex.runtime.settings import RuntimeSettingsStore

log = setup_logger("silex.api.server")

SKILL_RELOAD_DEBOUNCE_SEC = 2.0
_last_skill_reload_at = 0.0

# Routes reachable without the web API key. Kept minimal — even read-only
# routes like /api/graph and /api/metrics can leak memory content, so only
# a liveness probe is exempt.
_PUBLIC_PATHS = {"/api/health"}


class LocalAuthMiddleware(BaseHTTPMiddleware):
    """Defense-in-depth for the loopback-bound gateway.

    Binding to 127.0.0.1 stops LAN/remote access, but any browser tab the
    user has open (including a malicious website) can still reach
    127.0.0.1 directly. This middleware rejects requests that don't present
    the locally-generated web API key, closing that cross-origin/CSRF-style
    hole even though CORS already restricts *readable* responses.
    """

    async def dispatch(self, request: Request, call_next):
        if not gateway_auth_required() or request.url.path in _PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        expected = RuntimeSettingsStore().ensure_web_api_key()
        provided = request.headers.get("x-kinthic-api-key", "")
        if not provided:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()
        if not provided or not hmac.compare_digest(provided, expected):
            log.warning("Rejected unauthenticated gateway request: %s %s", request.method, request.url.path)
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return await call_next(request)

# The unified singleton cognitive brain
shared_loop: CognitiveLoop | None = None
db: Database | None = None

class ChatRequest(BaseModel):
    message: str
    images: Optional[List[Dict[str, Any]]] = None

class ApprovalRequest(BaseModel):
    approval_id: str
    approved: bool

class RestoreRequest(BaseModel):
    archive: str
    pre_backup: bool = True

class SkillNameRequest(BaseModel):
    name: str

MCP_TOOLS = [
    {"name": "silex_recall", "description": "Hybrid memory recall (recent + important + keyword + semantic RRF)."},
    {"name": "silex_search", "description": "Keyword FTS search across stored memories."},
    {"name": "silex_remember", "description": "Store memory through full A-MAC admission pipeline."},
    {"name": "silex_remember_explicit", "description": "Store a user/agent fact directly (bypasses A-MAC)."},
    {"name": "silex_forget", "description": "Delete a memory by ID (requires confirm=true)."},
    {"name": "silex_get_memory", "description": "Retrieve a single memory by UUID."},
    {"name": "silex_list_memories", "description": "List memories with pagination and optional tag filter."},
    {"name": "silex_graph_recall", "description": "Graph-aware causal context from the knowledge graph."},
    {"name": "silex_memory_health", "description": "Memory engine health: counts, vector drift, FTS availability."},
    {"name": "kinthic_skills_list", "description": "List loaded Kinthic workflow skills (compact index)."},
    {"name": "kinthic_skill_view", "description": "Load full markdown instructions for a named Kinthic skill."},
]

active_cancels: Dict[str, asyncio.Event] = {}
active_approvals: Dict[str, asyncio.Queue] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global shared_loop, db
    
    # 1. Initialize central database connection
    db = Database(str(SILEX_DB))
    await db.connect()
    
    # 2. Instantiate and start the central Cognitive Loop
    log.info("Starting Central Cognitive Loop...")
    shared_loop = CognitiveLoop()
    await shared_loop.startup()

    mcp = None
    try:
        from silex.mcp.server.app import mount_mcp_server
        mcp = mount_mcp_server(app, shared_loop)
    except ImportError as exc:
        log.warning("MCP server not mounted (install kinthic[mcp]): %s", exc)
    except Exception as exc:
        log.error("Failed to mount MCP server: %s", exc)
    
    # 3. Start Omnichannel Adapters
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        try:
            from silex.adapters.telegram import TelegramAdapter
            telegram = TelegramAdapter()
            await telegram.start_async(shared_loop)
            log.info("Telegram Adapter attached to Central Loop.")
        except Exception as e:
            log.error(f"Failed to attach Telegram Adapter: {e}")
            
    if os.getenv("DISCORD_BOT_TOKEN"):
        try:
            from silex.adapters.discord import DiscordAdapter
            discord_adapter = DiscordAdapter()
            await discord_adapter.start_async(shared_loop)
            log.info("Discord Adapter attached to Central Loop.")
        except Exception as e:
            log.error(f"Failed to attach Discord Adapter: {e}")

    if mcp is not None:
        async with mcp.session_manager.run():
            yield
    else:
        yield
    
    # Teardown
    log.info("Shutting down Central Cognitive Loop...")
    if shared_loop:
        await shared_loop.shutdown()
    if db:
        await db.close()


app = FastAPI(title="Kinthic Omnichannel Gateway", lifespan=lifespan)

# Order matters: Starlette applies middleware in reverse-registration order,
# so registering auth after CORS means auth runs first on the request path.
app.add_middleware(
    CORSMiddleware,
    allow_origins=gateway_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LocalAuthMiddleware)


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    """Unauthenticated liveness probe only — reveals no state."""
    return {"status": "ok"}


@app.get("/api/graph")
async def get_graph() -> Dict[str, Any]:
    """Fetch all epistemic nodes and edges for the graph visualization."""
    if not db:
        return {"error": "DB not initialized", "nodes": [], "edges": []}
        
    try:
        node_rows = await db.fetch_all("SELECT node_id, type, content, status FROM epistemic_nodes")
        nodes = [dict(row) for row in node_rows]
        
        edge_rows = await db.fetch_all("SELECT edge_id, source_node_id, target_node_id, relation_type FROM epistemic_edges")
        edges = [dict(row) for row in edge_rows]
        
        return {
            "nodes": nodes,
            "edges": edges,
        }
    except Exception as e:
        return {"error": str(e), "nodes": [], "edges": []}

@app.post("/api/chat/stream")
async def process_chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream cognitive loop events and responses."""
    if not shared_loop:
        return {"error": "Cognitive engine is not ready."}
        
    request_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    active_cancels[request_id] = cancel_event

    async def event_emitter(msg: dict):
        if cancel_event.is_set():
            raise asyncio.CancelledError("User cancelled stream")
            
        await queue.put(json.dumps(msg) + "\n")
        
        if msg.get("type") == "approval_requested":
            app_id = msg["data"]["approval_id"]
            app_queue = asyncio.Queue()
            active_approvals[app_id] = app_queue
            
            try:
                approved = await asyncio.wait_for(app_queue.get(), timeout=300.0)
            except asyncio.TimeoutError:
                approved = False
            finally:
                active_approvals.pop(app_id, None)
                
            await queue.put(json.dumps({
                "type": "approval_resolved",
                "data": {"approval_id": app_id, "approved": approved}
            }) + "\n")
            
            if not approved:
                raise Exception("User denied tool approval.")

    async def generator():
        task = asyncio.create_task(shared_loop.process(req.message, event_emitter=event_emitter, images=req.images))
        try:
            while True:
                get_task = asyncio.create_task(queue.get())
                done, pending = await asyncio.wait([get_task, task], return_when=asyncio.FIRST_COMPLETED)
                
                if get_task in done:
                    yield get_task.result()
                    queue.task_done()
                
                if task in done:
                    if not get_task.done():
                        get_task.cancel()
                    while not queue.empty():
                        yield queue.get_nowait()
                    
                    try:
                        res = task.result()
                        # Only yield response if we didn't stream it already, though event_emitter should cover it
                        if getattr(res, "response", "") and not queue.empty():
                            pass
                    except asyncio.CancelledError:
                        yield json.dumps({"type": "cancel", "data": {"message": "Thinking cancelled."}}) + "\n"
                    except Exception as e:
                        yield json.dumps({"type": "error", "data": {"message": str(e)}}) + "\n"
                    
                    yield json.dumps({"type": "done"}) + "\n"
                    break
        finally:
            if not task.done():
                log.info("Client disconnected from chat stream; cancelling background processing task.")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    log.warning(f"Error clean-cancelling background chat task: {exc}")
            active_cancels.pop(request_id, None)
                
    return StreamingResponse(generator(), media_type="application/x-ndjson", headers={"X-Request-Id": request_id})

@app.post("/api/chat/cancel")
async def cancel_chat(req: Request):
    data = await req.json()
    req_id = data.get("request_id")
    if req_id in active_cancels:
        active_cancels[req_id].set()
        return {"status": "cancelling"}
    return {"status": "not_found"}

@app.post("/api/chat/approve")
async def approve_chat(req: ApprovalRequest):
    if req.approval_id in active_approvals:
        await active_approvals[req.approval_id].put(req.approved)
        return {"status": "resolved"}
    return {"error": "Approval request not found or expired"}

@app.get("/api/skills")
async def get_skills() -> Dict[str, Any]:
    """List all loaded skills via SkillLoader (flat, nested, and plugin)."""
    loader = _get_skill_loader()
    if not loader:
        from silex.core.skills import SkillLoader
        loader = SkillLoader()
        loader.load_all()
    return {"skills": loader.list_skills_detailed(), "count": len(loader.skills)}


@app.get("/api/skills/catalog")
async def get_skills_catalog(q: Optional[str] = None) -> Dict[str, Any]:
    from silex.plugins.registry import get_registry

    registry = get_registry()
    if q:
        entries = registry.search(q.strip(), type_filter="skill")
    else:
        entries = registry.get_all(type_filter="skill")
    return {"entries": entries, "query": q}


@app.post("/api/skills/catalog/refresh")
async def refresh_skills_catalog() -> Dict[str, Any]:
    from silex.plugins.registry import get_registry

    ok, msg = get_registry().refresh_from_remote()
    if not ok:
        raise HTTPException(status_code=502, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/skills/install")
async def install_skill(req: SkillNameRequest) -> Dict[str, Any]:
    from silex.plugins.registry import get_registry

    ok, msg = get_registry().install(req.name.strip())
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    loader = _get_skill_loader()
    count = loader.load_all() if loader else 0
    return {"ok": True, "message": msg, "loaded_count": count}


@app.post("/api/skills/uninstall")
async def uninstall_skill(req: SkillNameRequest) -> Dict[str, Any]:
    from silex.plugins.registry import get_registry

    ok, msg = get_registry().uninstall(req.name.strip())
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    loader = _get_skill_loader()
    count = loader.load_all() if loader else 0
    return {"ok": True, "message": msg, "loaded_count": count}


@app.post("/api/skills/reload")
async def reload_skills() -> Dict[str, Any]:
    global _last_skill_reload_at
    loader = _get_skill_loader()
    if not loader:
        from silex.core.skills import SkillLoader
        loader = SkillLoader()

    now = time.monotonic()
    if now - _last_skill_reload_at < SKILL_RELOAD_DEBOUNCE_SEC:
        return {
            "ok": True,
            "loaded_count": len(loader.skills),
            "debounced": True,
        }

    _last_skill_reload_at = now
    count = loader.load_all()
    return {"ok": True, "loaded_count": count, "debounced": False}


@app.get("/api/skills/{name}")
async def get_skill_detail(name: str) -> Dict[str, Any]:
    loader = _get_skill_loader()
    if not loader:
        from silex.core.skills import SkillLoader
        loader = SkillLoader()
        loader.load_all()
    body = loader.get_skill_body(name)
    if body is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    meta = loader.skill_meta.get(name)
    detail = next((s for s in loader.list_skills_detailed() if s["name"] == name), None)
    return {
        "name": name,
        "body": body,
        "metadata": detail or {},
        "trust_level": meta.trust_level if meta else "community",
    }


def _get_skill_loader():
    if shared_loop is not None and hasattr(shared_loop, "skill_loader"):
        return shared_loop.skill_loader
    return None


@app.get("/api/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Fetch system metrics from the database."""
    if not db:
        return {"error": "DB not initialized"}
    
    try:
        nodes_count = (await db.fetch_one("SELECT COUNT(*) as c FROM epistemic_nodes"))["c"]
        edges_count = (await db.fetch_one("SELECT COUNT(*) as c FROM epistemic_edges"))["c"]
        memories_count = (await db.fetch_one("SELECT COUNT(*) as c FROM memories"))["c"]
        trajectories_count = (await db.fetch_one("SELECT COUNT(*) as c FROM trajectories"))["c"]

        vector_drift = -1
        if shared_loop is not None:
            try:
                vector_drift = await shared_loop.memory.get_vector_drift_count()
            except Exception as e:
                log.warning("Failed to compute vector drift for /api/metrics: %s", e)

        from silex.ops.backup import daemon_is_running

        mcp_mounted = False
        try:
            from silex.mcp.server.app import get_mcp_fastmcp
            mcp_mounted = get_mcp_fastmcp() is not None
        except ImportError:
            pass

        skills_loaded = 0
        if shared_loop is not None and hasattr(shared_loop, "skill_loader"):
            skills_loaded = len(shared_loop.skill_loader.skills)

        return {
            "nodes": nodes_count,
            "edges": edges_count,
            "memories": memories_count,
            "trajectories": trajectories_count,
            "skills_loaded": skills_loaded,
            "vector_drift": vector_drift,
            "writer_dead": bool(getattr(db, "_writer_dead", False)),
            "daemon_running": daemon_is_running(),
            "mcp_server": mcp_mounted,
            "mcp_tools": len(MCP_TOOLS),
            "mcp_endpoint": "/mcp",
        }
    except Exception as e:
        return {"error": str(e)}


def _memory_to_dict(memory) -> Dict[str, Any]:
    memory_type = memory.memory_type
    if hasattr(memory_type, "value"):
        memory_type = memory_type.value
    source = memory.source
    if hasattr(source, "value"):
        source = source.value
    return {
        "id": memory.id,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "memory_type": memory_type,
        "source": source,
        "tags": memory.tags,
        "created_at": memory.created_at,
        "last_accessed": memory.last_accessed,
        "access_count": memory.access_count,
    }


def _validate_backup_path(archive: str) -> Path:
    path = Path(archive).expanduser().resolve()
    backups_dir = KINTHIC_BACKUPS.resolve()
    try:
        path.relative_to(backups_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Archive must be inside the backup directory") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Archive path is not a file")
    return path


@app.get("/api/memories")
async def list_memories(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    tag: Optional[str] = None,
    q: Optional[str] = None,
) -> Dict[str, Any]:
    if not shared_loop:
        return {"memories": [], "total": 0, "error": "Cognitive engine is not ready."}

    store = shared_loop.memory
    try:
        if q:
            results = await store.search(q.strip())
            total = len(results)
            page = results[offset : offset + limit]
            return {"memories": [_memory_to_dict(m) for m in page], "total": total, "query": q}
        memories, total = await store.list_page(offset=offset, limit=limit, tag=tag or None)
        return {"memories": [_memory_to_dict(m) for m in memories], "total": total, "tag": tag}
    except Exception as e:
        log.error("Failed to list memories: %s", e)
        return {"memories": [], "total": 0, "error": str(e)}


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str, confirm: bool = Query(False)) -> Dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to delete a memory")
    if not shared_loop:
        raise HTTPException(status_code=503, detail="Cognitive engine is not ready")

    deleted = await shared_loop.memory.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "id": memory_id}


@app.get("/api/backups")
async def list_backups() -> Dict[str, Any]:
    KINTHIC_BACKUPS.mkdir(parents=True, exist_ok=True)
    backups: List[Dict[str, Any]] = []
    for file_path in sorted(KINTHIC_BACKUPS.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = file_path.stat()
        backups.append(
            {
                "name": file_path.name,
                "path": str(file_path.resolve()),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return {"backups": backups, "backup_dir": str(KINTHIC_BACKUPS.resolve())}


@app.post("/api/backups")
async def create_backup() -> Dict[str, Any]:
    from silex.ops.backup import export_backup

    KINTHIC_BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = KINTHIC_BACKUPS / f"kinthic-backup-{stamp}.zip"
    try:
        await asyncio.to_thread(export_backup, str(out_path))
    except Exception as e:
        log.error("Backup failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    stat = out_path.stat()
    return {
        "name": out_path.name,
        "path": str(out_path.resolve()),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


@app.post("/api/restore/preview")
async def restore_preview(req: RestoreRequest) -> Dict[str, Any]:
    from silex.ops.backup import inspect_backup

    path = _validate_backup_path(req.archive)
    return inspect_backup(path)


@app.post("/api/restore/apply")
async def restore_apply(req: RestoreRequest) -> Dict[str, Any]:
    from silex.ops.backup import daemon_is_running, restore_backup

    path = _validate_backup_path(req.archive)
    if daemon_is_running():
        raise HTTPException(
            status_code=409,
            detail="Stop the Kinthic daemon first (kinthic stop), then restore.",
        )

    try:
        summary = await asyncio.to_thread(
            restore_backup,
            path,
            apply=True,
            pre_backup=req.pre_backup,
        )
    except Exception as e:
        log.error("Restore failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if summary.get("errors"):
        raise HTTPException(status_code=400, detail=summary["errors"])

    return {
        **summary,
        "restart_required": True,
        "message": "Restore complete. Restart kinthic web or the daemon to load the restored data.",
    }


@app.get("/api/integrations")
async def get_integrations() -> Dict[str, Any]:
    from silex.mcp.server.print_config import claude_desktop_config, cursor_config

    mcp_mounted = False
    try:
        from silex.mcp.server.app import get_mcp_fastmcp
        mcp_mounted = get_mcp_fastmcp() is not None
    except ImportError:
        pass

    host = gateway_host()
    port = gateway_port()
    return {
        "mcp_active": mcp_mounted,
        "http_endpoint": f"http://{host}:{port}/mcp",
        "health_endpoint": f"http://{host}:{port}/api/health",
        "stdio_command": "kinthic mcp serve --stdio",
        "stdio_command_python": f'python -m scripts.cli mcp serve --stdio',
        "claude_config": claude_desktop_config(),
        "cursor_config": cursor_config(),
        "tools": MCP_TOOLS,
    }


@app.get("/api/settings")
async def get_settings() -> Dict[str, Any]:
    store = RuntimeSettingsStore()
    return store.load_settings()

@app.post("/api/settings")
async def save_settings(req: Request) -> Dict[str, Any]:
    try:
        data = await req.json()
        store = RuntimeSettingsStore()
        updated = store.save_settings(data)
        return updated
    except Exception as e:
        log.error(f"Failed to save settings: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    from silex.utils.config import gateway_host, gateway_port
    uvicorn.run(app, host=gateway_host(), port=gateway_port())
