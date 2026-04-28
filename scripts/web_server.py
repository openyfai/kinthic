"""
ARIA Knowledge Graph Visualizer — Web Server.

Security: Binds to localhost by default. Optional API key authentication.
Uses a shared DB/KG instance via FastAPI lifespan (not per-request creation).
"""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aria.storage.database import Database
from aria.world.graph import KnowledgeGraph

# ---------------------------------------------------------------------------
# Shared state (populated during lifespan)
# ---------------------------------------------------------------------------

_db: Database | None = None
_kg: KnowledgeGraph | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — create a single DB + KG instance."""
    global _db, _kg
    _db = Database()
    await _db.connect()
    _kg = KnowledgeGraph(_db)
    await _kg.load()
    yield
    if _db:
        await _db.close()


app = FastAPI(title="ARIA Knowledge Graph Visualizer", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

_API_KEY = os.getenv("ARIA_WEB_API_KEY", "")


def _check_auth(authorization: str | None):
    """Validate API key if one is configured."""
    if not _API_KEY:
        return  # No key configured — allow (localhost only)
    if authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the static HTML visualization page."""
    index_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "aria", "ui", "static", "index.html"
    )
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)


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


if __name__ == "__main__":
    host = os.getenv("ARIA_WEB_HOST", "127.0.0.1")  # Localhost by default
    port = int(os.getenv("ARIA_WEB_PORT", "8000"))
    print(f"🚀 Starting ARIA Knowledge Graph Visualizer on http://{host}:{port}")
    if not _API_KEY:
        print("ℹ️  No ARIA_WEB_API_KEY set — running without authentication (localhost only).")
    uvicorn.run(app, host=host, port=port)
