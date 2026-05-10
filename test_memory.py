import asyncio
from aria.storage.database import Database
from aria.memory.memory_store import MemoryStore
from aria.models.schemas import NewMemory

async def test():
    print("Testing NewMemory validation...")
    try:
        nm = NewMemory(content="The user's favorite color is OLED black.", importance="core")
        print(f"NewMemory created with importance: {nm.importance}")
    except Exception as e:
        print(f"NewMemory creation failed: {e}")
        
    db = Database(":memory:")
    await db.connect()
    
    ms = MemoryStore(db)
    
    print("\nTesting memory storage and vector sync...")
    # Add a memory
    mem1 = await ms.add_manual("The user prefers Apple-style spring animations.", importance=0.9)
    print(f"Stored mem1: {mem1.id} with importance {mem1.importance}")
    
    # Test vector sync retrieval
    print("\nTesting semantic retrieval...")
    ctx = await ms.retrieve_context("Apple animations")
    print(f"Retrieved {len(ctx)} memories.")
    for m in ctx:
        print(f" -> {m.content}")

    # Test decay
    print("\nTesting memory decay...")
    await ms.decay_importance(days=0, decay_factor=0.5)
    mem_after = await ms.get(mem1.id)
    print(f"Importance after decay: {mem_after.importance}")
    
    # Test deduplication
    print("\nTesting duplicate detection...")
    is_dup = await ms._is_duplicate("The user really likes Apple-style spring animations.")
    print(f"Is duplicate? {is_dup}")

if __name__ == "__main__":
    asyncio.run(test())
