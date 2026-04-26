import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aria.storage.database import Database
from aria.world.graph import KnowledgeGraph

app = FastAPI(title="ARIA Knowledge Graph Visualizer")

# Serve the static HTML page at the root
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aria", "ui", "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/api/graph")
async def get_graph_data():
    """Returns the nodes and edges from the SQLite database."""
    db = Database()
    await db.initialize()
    
    kg = KnowledgeGraph(db)
    await kg.load()
    
    nodes = []
    edges = []
    
    for node_id, data in kg.graph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "label": data.get("content", ""),
            "group": data.get("node_type", "fact"),
            "val": data.get("confidence", 0.5) * 10  # Size factor for visualizer
        })
        
    for u, v, data in kg.graph.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "label": data.get("edge_type", "related"),
            "strength": data.get("strength", 0.5)
        })
        
    await db.close()
    
    return {
        "nodes": nodes,
        "links": edges
    }

if __name__ == "__main__":
    print("🚀 Starting ARIA Knowledge Graph Visualizer on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
