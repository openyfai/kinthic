import asyncio
import time
import os
import sys
from silex.storage.database import Database
from silex.memory.memory_store import MemoryStore
from silex.core.saga import AutonomousSagaOrchestrator, SagaContext

async def mock_action(context, duration=1.0):
    await asyncio.sleep(duration)

async def mock_compensate(context):
    pass

async def test_dag():
    print("[CHAOS TEST] Testing DAG Parallel Execution...")
    db = Database(f"test_dag_{os.getpid()}.db")
    await db.connect()
    
    # Initialize DB schema for telemetry
    await db.execute("""
        CREATE TABLE IF NOT EXISTS saga_telemetry_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saga_id TEXT,
            status TEXT,
            current_step TEXT,
            created_at TEXT
        )
    """)
    
    orchestrator = AutonomousSagaOrchestrator(db)
    
    # Register steps
    orchestrator.register_step("A", lambda c: mock_action(c, 1.0), mock_compensate, depends_on=[])
    orchestrator.register_step("B", lambda c: mock_action(c, 1.0), mock_compensate, depends_on=[])
    orchestrator.register_step("C", lambda c: mock_action(c, 1.0), mock_compensate, depends_on=[])
    orchestrator.register_step("D", lambda c: mock_action(c, 0.1), mock_compensate, depends_on=["A", "B", "C"])
    
    context = SagaContext()
    
    start_time = time.time()
    res = await orchestrator.execute(context)
    end_time = time.time()
    
    duration = end_time - start_time
    
    if duration < 2.0:
        print(f"[CHAOS TEST] DAG SUCCESS. Completed 3.1s of compute in {duration:.2f}s due to parallel execution.")
    else:
        print(f"[CHAOS TEST] DAG FAILED. Took {duration:.2f}s, which means it ran sequentially.")
        sys.exit(1)

async def test_entropy():
    print("[CHAOS TEST] Testing Graph Entropy Decay...")
    db = Database(f"test_entropy_{os.getpid()}.db")
    await db.connect()
    
    # Silex creates schema inside MemoryStore init usually, but we'll use MemoryStore
    store = MemoryStore(db)
    
    # Insert an old node
    await db.execute("""
        INSERT INTO knowledge_nodes (id, content, node_type, confidence, created_at, last_validated)
        VALUES (?, ?, ?, ?, datetime('now', '-30 days'), datetime('now', '-30 days'))
    """, ("old_node_id", "The earth is flat.", "fact", 0.11))
    
    # Insert a new node
    await db.execute("""
        INSERT INTO knowledge_nodes (id, content, node_type, confidence, created_at, last_validated)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
    """, ("new_node_id", "The earth is round.", "fact", 0.11))
    
    # Trigger decay
    await store.decay_graph_entropy(days=14, decay_factor=0.8, absolute_threshold=0.1)
    
    # Assertions
    rows = await db.fetch_all("SELECT id, confidence FROM knowledge_nodes")
    ids = [r["id"] for r in rows]
    
    if "old_node_id" not in ids and "new_node_id" in ids:
        print("[CHAOS TEST] ENTROPY SUCCESS. Old node was hard-purged, new node survived.")
    else:
        print(f"[CHAOS TEST] ENTROPY FAILED. Remaining nodes: {ids}")
        sys.exit(1)

async def main():
    await test_dag()
    await test_entropy()

if __name__ == "__main__":
    asyncio.run(main())
