import asyncio
import json
from typing import List, Tuple
from silex.models.schemas import KnowledgeNode, CausalEdge, Memory
from silex.storage.database import Database
from silex.utils.logger import setup_logger

log = setup_logger("silex.graph_buffer")

class GraphTransactionBuffer:
    """
    Volatile memory buffer that hoards writes and flushes them to SQLite in a massive atomic transaction.
    Derived from the UNWIND batch-writing physics to prevent disk I/O bottlenecks.
    """
    def __init__(self, db: Database):
        self.db = db
        self._nodes: List[KnowledgeNode] = []
        self._edges: List[CausalEdge] = []
        self._memories: List[Memory] = []
        self._raw_queries: List[Tuple[str, tuple]] = []
        self._lock = asyncio.Lock()

    async def stage_node(self, node: KnowledgeNode) -> None:
        async with self._lock:
            self._nodes.append(node)

    async def stage_edge(self, edge: CausalEdge) -> None:
        async with self._lock:
            self._edges.append(edge)

    async def stage_memory(self, memory: Memory) -> None:
        async with self._lock:
            self._memories.append(memory)
            
    async def stage_raw_query(self, query: str, params: tuple) -> None:
        async with self._lock:
            self._raw_queries.append((query, params))

    async def commit_flush(self) -> None:
        """
        Atomically flush all staged nodes, edges, and memories to SQLite using executemany.
        """
        async with self._lock:
            if not self._nodes and not self._edges and not self._memories and not self._raw_queries:
                return

            try:
                # Use executemany for atomic batch inserts (UNWIND pattern)
                async with self.db._conn.execute("BEGIN TRANSACTION"):
                    for query, params in self._raw_queries:
                        await self.db._conn.execute(query, params)
                        
                    if self._memories:
                        memory_data = [
                            (
                                m.id, m.content, m.source.value if hasattr(m.source, 'value') else m.source,
                                m.memory_type.value if hasattr(m.memory_type, 'value') else m.memory_type,
                                m.importance, m.confidence, m.created_at, m.last_accessed,
                                m.access_count, json.dumps(m.tags), m.level, json.dumps(m.child_memory_ids),
                                json.dumps(m.provenance), json.dumps(m.related_memories), m.archived_at,
                                None # content_fingerprint
                            ) for m in self._memories
                        ]
                        await self.db._conn.executemany(
                            """
                            INSERT OR REPLACE INTO memories (
                                id, content, source, memory_type, importance, confidence,
                                created_at, last_accessed, access_count, tags, level,
                                child_memory_ids, provenance_json, related_memories, archived_at, content_fingerprint
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, memory_data
                        )

                    if self._nodes:
                        node_data = [
                            (
                                n.id, n.content, n.node_type.value if hasattr(n.node_type, 'value') else n.node_type,
                                n.confidence, n.source, n.created_at, n.last_validated,
                                n.validation_count, n.contradiction_count,
                                n.verification_status.value if hasattr(n.verification_status, 'value') else n.verification_status,
                                json.dumps(n.metadata)
                            ) for n in self._nodes
                        ]
                        await self.db._conn.executemany(
                            """
                            INSERT OR REPLACE INTO knowledge_nodes (
                                id, content, node_type, confidence, source, created_at,
                                last_validated, validation_count, contradiction_count,
                                verification_status, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, node_data
                        )

                    if self._edges:
                        edge_data = [
                            (
                                e.id, e.source_node, e.target_node,
                                e.edge_type.value if hasattr(e.edge_type, 'value') else e.edge_type,
                                e.strength, e.evidence, e.created_at
                            ) for e in self._edges
                        ]
                        await self.db._conn.executemany(
                            """
                            INSERT OR REPLACE INTO causal_edges (
                                id, source_node, target_node, edge_type, strength, evidence, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, edge_data
                        )

                    await self.db._conn.commit()

                log.info(f"Batched Flush Complete: {len(self._memories)} memories, {len(self._nodes)} nodes, {len(self._edges)} edges.")
            except Exception as e:
                log.error(f"Batch flush failed: {e}")
                await self.db._conn.rollback()
                raise
            finally:
                # Clear buffers
                self._nodes.clear()
                self._edges.clear()
                self._memories.clear()
                self._raw_queries.clear()
