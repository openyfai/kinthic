import asyncio
import os
import sys
from silex.storage.database import Database
from silex.memory.memory_store import MemoryStore
from silex.models.schemas import KnowledgeNode, NodeType


async def mock_novelty(x):
    return 1.0


async def run_chaos_test():
    print("[CHAOS TEST] Booting temporary Silex Kernel...")

    db_path = f"chaos_test_graph_{os.getpid()}.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(db_path + "-wal"):
        os.remove(db_path + "-wal")

    db = Database(db_path)
    await db.connect()

    mem_store = MemoryStore(db)

    # Simulate 500 iterations of a chaotic loop inferring the same fact
    print(
        "[CHAOS TEST] Injecting 500 identical nodes to trigger duplicate collision..."
    )

    concept = "The sky is blue"

    for i in range(500):
        node = KnowledgeNode(content=concept, node_type=NodeType.FACT)
        # Using the private method of the graph buffer for testing, or we just stage it
        await mem_store.buffer.stage_node(node)

    print("[CHAOS TEST] Staged 500 nodes. Triggering atomic flush...")
    await mem_store.flush()

    # Assertions
    rows = await db.fetch_all("SELECT count(*) as c FROM knowledge_nodes")
    row_count = rows[0]["c"]

    if row_count == 1:
        print(
            f"[CHAOS TEST] SUCCESS. 500 nodes collapsed into exactly {row_count} row via UUID5 determinism."
        )
    else:
        print(f"[CHAOS TEST] FAILED. Expected 1 row, got {row_count} rows.")
        sys.exit(1)

    # Test payload gating
    print("[CHAOS TEST] Injecting bloated payload into A-MAC...")
    bloated_payload = "A" * 5000
    res = await mem_store.amac.evaluate_admission(
        bloated_payload, "fact", "", mock_novelty
    )

    if len(res.get("sanitized_content", "")) <= 850:
        print("[CHAOS TEST] SUCCESS. Payload gating truncated the 5000-byte payload.")
    else:
        print(
            f"[CHAOS TEST] FAILED. Payload was not truncated properly. Length: {len(res.get('sanitized_content', ''))}"
        )
        sys.exit(1)

    await db.close()


if __name__ == "__main__":
    asyncio.run(run_chaos_test())
