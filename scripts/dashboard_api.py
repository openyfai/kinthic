from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from silex.storage.database import Database
from silex.utils.config import SILEX_DB

# We instantiate a fresh read-only Database instance
db_path = SILEX_DB
db = Database(str(db_path))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    await db.connect()
    yield
    # Teardown
    await db.close()

app = FastAPI(title="Kinthic Dashboard API", lifespan=lifespan)

# Allow CORS for the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/graph")
async def get_graph() -> Dict[str, Any]:
    """Fetch all epistemic nodes and edges for the graph visualization."""
    try:
        # Fetch nodes
        node_rows = await db.fetch_all("SELECT node_id, type, content, status FROM epistemic_nodes")
        nodes = [dict(row) for row in node_rows]
        
        # Fetch edges
        edge_rows = await db.fetch_all("SELECT edge_id, source_node_id, target_node_id, relation_type FROM epistemic_edges")
        edges = [dict(row) for row in edge_rows]
        
        return {
            "nodes": nodes,
            "edges": edges,
        }
    except Exception as e:
        return {"error": str(e), "nodes": [], "edges": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
