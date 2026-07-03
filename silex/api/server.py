from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import os
import json
import uuid
import asyncio

from silex.storage.database import Database
from silex.utils.config import SILEX_DB
from typing import Dict, Any, List, Optional
import os
import json
import uuid
import asyncio

from silex.storage.database import Database
from silex.utils.config import SILEX_DB
from silex.core.cognitive_loop import CognitiveLoop
from silex.utils.logger import setup_logger
from silex.runtime.settings import RuntimeSettingsStore

log = setup_logger("silex.api.server")

# The unified singleton cognitive brain
shared_loop: CognitiveLoop | None = None
db: Database | None = None

class ChatRequest(BaseModel):
    message: str
    images: Optional[List[Dict[str, Any]]] = None

class ApprovalRequest(BaseModel):
    approval_id: str
    approved: bool

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

    yield
    
    # Teardown
    log.info("Shutting down Central Cognitive Loop...")
    if shared_loop:
        await shared_loop.shutdown()
    if db:
        await db.close()


app = FastAPI(title="Kinthic Omnichannel Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Fetch all synthesized skills from the skills directory."""
    from silex.utils.config import KINTHIC_HOME
    skills_dir = KINTHIC_HOME / "skills"
    if not skills_dir.exists():
        return {"skills": []}
    
    skills = []
    for file in skills_dir.glob("*.md"):
        if file.name == "SKILL.md":
            continue
        try:
            content = file.read_text(encoding="utf-8")
            # Extract title and description from markdown if possible, or just send raw content
            lines = content.split("\n")
            title = lines[0].replace("#", "").strip() if lines and lines[0].startswith("#") else file.name
            skills.append({
                "name": file.name,
                "title": title,
                "size": file.stat().st_size,
                "preview": content[:200] + "..."
            })
        except Exception:
            pass
    return {"skills": skills}

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
        
        return {
            "nodes": nodes_count,
            "edges": edges_count,
            "memories": memories_count,
            "trajectories": trajectories_count
        }
    except Exception as e:
        return {"error": str(e)}

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
