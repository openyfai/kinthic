"""
Knowledge Graph Engine — ARIA's causal world model.

Uses NetworkX as an in-memory directed graph with SQLite persistence.
Every piece of knowledge is a node. Relationships are typed edges
(causes, enables, requires, contradicts, supports, part_of, similar_to, temporal).

The graph is loaded from SQLite on startup and saved on shutdown.
All mutations go through SQLite first (source of truth), then update the
in-memory graph.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import networkx as nx

from aria.models.schemas import (
    CausalEdge,
    EdgeType,
    KnowledgeNode,
    NodeType,
)
from aria.storage.database import Database
from aria.utils.logger import setup_logger

log = setup_logger("aria.world.graph")


class KnowledgeGraph:
    """
    NetworkX-backed causal knowledge graph.

    Nodes are knowledge (facts, concepts, entities).
    Edges are typed causal relationships.
    """

    def __init__(self, db: Database):
        self.db = db
        self.graph: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Load the graph from SQLite into memory."""
        # Load nodes
        node_rows = await self.db.fetch_all(
            "SELECT * FROM knowledge_nodes ORDER BY created_at"
        )
        for row in node_rows:
            self.graph.add_node(
                row["id"],
                content=row["content"],
                node_type=row["node_type"],
                confidence=row["confidence"],
                source=row["source"],
                created_at=row["created_at"],
                last_validated=row["last_validated"],
                validation_count=row["validation_count"],
                contradiction_count=row["contradiction_count"],
                metadata=json.loads(row["metadata"]),
            )

        # Load edges
        edge_rows = await self.db.fetch_all(
            "SELECT * FROM causal_edges ORDER BY created_at"
        )
        for row in edge_rows:
            if row["source_node"] in self.graph and row["target_node"] in self.graph:
                self.graph.add_edge(
                    row["source_node"],
                    row["target_node"],
                    id=row["id"],
                    edge_type=row["edge_type"],
                    strength=row["strength"],
                    evidence=row["evidence"],
                    created_at=row["created_at"],
                )

        log.info(
            f"Knowledge graph loaded: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )

    # ------------------------------------------------------------------
    # Node Operations
    # ------------------------------------------------------------------

    async def add_node(self, node: KnowledgeNode) -> KnowledgeNode:
        """Add a knowledge node to the graph and database."""
        # Check for near-duplicate
        existing = await self.find_similar_node(node.content)
        if existing:
            # Reinforce existing node instead of creating duplicate
            await self._reinforce_node(existing)
            log.debug(f"Reinforced existing node: {existing[:40]}...")
            return self._get_node_model(existing)

        # Persist to SQLite
        node_type = node.node_type.value if isinstance(node.node_type, NodeType) else node.node_type
        await self.db.execute(
            """
            INSERT INTO knowledge_nodes (id, content, node_type, confidence, source,
                                         created_at, last_validated, validation_count,
                                         contradiction_count, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id, node.content, node_type, node.confidence,
                node.source, node.created_at, node.last_validated,
                node.validation_count, node.contradiction_count,
                json.dumps(node.metadata),
            ),
        )

        # Add to in-memory graph
        self.graph.add_node(
            node.id,
            content=node.content,
            node_type=node_type,
            confidence=node.confidence,
            source=node.source,
            created_at=node.created_at,
            last_validated=node.last_validated,
            validation_count=node.validation_count,
            contradiction_count=node.contradiction_count,
            metadata=node.metadata,
        )

        log.debug(f"Added node: {node.content[:50]}...")
        return node

    async def find_similar_node(self, content: str, threshold: float = 0.8) -> str | None:
        """Find an existing node with very similar content. Returns node ID or None."""
        content_words = set(content.lower().strip().split())
        if not content_words:
            return None

        for node_id, data in self.graph.nodes(data=True):
            existing_words = set(data["content"].lower().strip().split())
            if not existing_words:
                continue
            overlap = content_words & existing_words
            smaller = min(len(content_words), len(existing_words))
            if smaller > 0 and len(overlap) / smaller >= threshold:
                return node_id

        return None

    async def _reinforce_node(self, node_id: str) -> None:
        """Increase validation count and update timestamp for a reinforced node."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE knowledge_nodes
            SET validation_count = validation_count + 1, last_validated = ?
            WHERE id = ?
            """,
            (now, node_id),
        )
        if node_id in self.graph:
            self.graph.nodes[node_id]["validation_count"] += 1
            self.graph.nodes[node_id]["last_validated"] = now

    async def update_confidence(self, node_id: str, new_confidence: float) -> None:
        """Update a node's confidence score."""
        await self.db.execute(
            "UPDATE knowledge_nodes SET confidence = ? WHERE id = ?",
            (new_confidence, node_id),
        )
        if node_id in self.graph:
            self.graph.nodes[node_id]["confidence"] = new_confidence

    async def increment_contradictions(self, node_id: str) -> None:
        """Increment contradiction count for a node."""
        await self.db.execute(
            """
            UPDATE knowledge_nodes
            SET contradiction_count = contradiction_count + 1
            WHERE id = ?
            """,
            (node_id,),
        )
        if node_id in self.graph:
            self.graph.nodes[node_id]["contradiction_count"] += 1

    def get_node(self, node_id: str) -> dict | None:
        """Get a node's data from the in-memory graph."""
        if node_id in self.graph:
            return {"id": node_id, **self.graph.nodes[node_id]}
        return None

    def _get_node_model(self, node_id: str) -> KnowledgeNode:
        """Convert an in-memory node to a KnowledgeNode model."""
        data = self.graph.nodes[node_id]
        return KnowledgeNode(
            id=node_id,
            content=data["content"],
            node_type=data["node_type"],
            confidence=data["confidence"],
            source=data["source"],
            created_at=data["created_at"],
            last_validated=data["last_validated"],
            validation_count=data["validation_count"],
            contradiction_count=data["contradiction_count"],
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Edge Operations
    # ------------------------------------------------------------------

    async def add_edge(self, edge: CausalEdge) -> CausalEdge:
        """Add a causal edge between two nodes."""
        # Ensure both nodes exist
        if edge.source_node not in self.graph or edge.target_node not in self.graph:
            log.warning(
                f"Cannot add edge: nodes not found "
                f"(src={edge.source_node[:8]}, tgt={edge.target_node[:8]})"
            )
            return edge

        # Check for duplicate edge
        if self.graph.has_edge(edge.source_node, edge.target_node):
            existing = self.graph.edges[edge.source_node, edge.target_node]
            if existing.get("edge_type") == (edge.edge_type.value if isinstance(edge.edge_type, EdgeType) else edge.edge_type):
                # Same type edge already exists — reinforce strength
                new_strength = min(1.0, existing.get("strength", 0.5) + 0.1)
                self.graph.edges[edge.source_node, edge.target_node]["strength"] = new_strength
                await self.db.execute(
                    "UPDATE causal_edges SET strength = ? WHERE source_node = ? AND target_node = ?",
                    (new_strength, edge.source_node, edge.target_node),
                )
                log.debug("Reinforced existing edge")
                return edge

        edge_type = edge.edge_type.value if isinstance(edge.edge_type, EdgeType) else edge.edge_type

        # Persist to SQLite
        await self.db.execute(
            """
            INSERT INTO causal_edges (id, source_node, target_node, edge_type,
                                      strength, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge.id, edge.source_node, edge.target_node,
                edge_type, edge.strength, edge.evidence, edge.created_at,
            ),
        )

        # Add to in-memory graph
        self.graph.add_edge(
            edge.source_node, edge.target_node,
            id=edge.id,
            edge_type=edge_type,
            strength=edge.strength,
            evidence=edge.evidence,
            created_at=edge.created_at,
        )

        src_content = self.graph.nodes[edge.source_node]["content"][:30]
        tgt_content = self.graph.nodes[edge.target_node]["content"][:30]
        log.debug(f"Added edge: {src_content} --[{edge_type}]--> {tgt_content}")
        return edge

    # ------------------------------------------------------------------
    # Graph Queries
    # ------------------------------------------------------------------

    def get_neighborhood(self, node_id: str, depth: int = 2) -> dict:
        """
        Get the causal neighborhood of a node.

        Returns all nodes and edges within `depth` hops, in both directions.
        """
        if node_id not in self.graph:
            return {"center": None, "nodes": [], "edges": []}

        # Collect nodes within depth (both predecessors and successors)
        nearby_nodes = set()
        nearby_nodes.add(node_id)

        frontier = {node_id}
        for _ in range(depth):
            next_frontier = set()
            for n in frontier:
                next_frontier.update(self.graph.predecessors(n))
                next_frontier.update(self.graph.successors(n))
            nearby_nodes.update(next_frontier)
            frontier = next_frontier

        # Build result
        nodes = []
        for nid in nearby_nodes:
            data = self.graph.nodes[nid]
            nodes.append({
                "id": nid,
                "content": data["content"],
                "type": data["node_type"],
                "confidence": data["confidence"],
            })

        edges = []
        for u, v, data in self.graph.edges(data=True):
            if u in nearby_nodes and v in nearby_nodes:
                edges.append({
                    "from": self.graph.nodes[u]["content"][:40],
                    "to": self.graph.nodes[v]["content"][:40],
                    "type": data.get("edge_type", "unknown"),
                    "strength": data.get("strength", 0.5),
                })

        return {
            "center": self.graph.nodes[node_id]["content"],
            "nodes": nodes,
            "edges": edges,
        }

    def find_causal_chain(self, source_id: str, target_id: str) -> list[dict] | None:
        """
        Find the shortest causal path between two nodes.

        Returns a list of steps, or None if no path exists.
        """
        if source_id not in self.graph or target_id not in self.graph:
            return None

        try:
            path = nx.shortest_path(self.graph, source_id, target_id)
        except nx.NetworkXNoPath:
            return None

        steps = []
        for i in range(len(path) - 1):
            edge_data = self.graph.edges[path[i], path[i + 1]]
            steps.append({
                "from": self.graph.nodes[path[i]]["content"],
                "relationship": edge_data.get("edge_type", "→"),
                "to": self.graph.nodes[path[i + 1]]["content"],
                "strength": edge_data.get("strength", 0.5),
            })

        return steps

    def find_node_by_content(self, query: str) -> str | None:
        """Find a node ID by partial content match."""
        query_lower = query.lower().strip()
        best_match = None
        best_overlap = 0

        for node_id, data in self.graph.nodes(data=True):
            content_lower = data["content"].lower()
            if query_lower in content_lower:
                # Exact substring match — return immediately
                return node_id
            # Word overlap
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = node_id

        if best_overlap >= 2:
            return best_match
        return None

    def get_contradicting_nodes(self, node_id: str) -> list[dict]:
        """Find all nodes that contradict a given node."""
        results = []
        for u, v, data in self.graph.edges(data=True):
            if data.get("edge_type") == "contradicts":
                if u == node_id:
                    results.append({"id": v, **self.graph.nodes[v]})
                elif v == node_id:
                    results.append({"id": u, **self.graph.nodes[u]})
        return results

    # ------------------------------------------------------------------
    # Context Retrieval (replaces flat keyword search)
    # ------------------------------------------------------------------

    async def retrieve_relevant_context(self, query: str, max_nodes: int = 15) -> list[dict]:
        """
        Graph-aware context retrieval.

        Given a query, find relevant nodes and their causal neighborhoods.
        This replaces the flat keyword search from Phase 1.
        """
        if self.graph.number_of_nodes() == 0:
            return []

        # Find directly relevant nodes via content matching
        query_words = set(query.lower().split())
        scored_nodes: list[tuple[str, float]] = []

        for node_id, data in self.graph.nodes(data=True):
            content_words = set(data["content"].lower().split())
            if not content_words:
                continue

            # Score = word overlap + confidence bonus + connection bonus
            overlap = len(query_words & content_words) / max(len(query_words), 1)
            confidence_bonus = data.get("confidence", 0.5) * 0.2
            degree_bonus = min(self.graph.degree(node_id) * 0.05, 0.3)

            score = overlap + confidence_bonus + degree_bonus
            if score > 0.1:
                scored_nodes.append((node_id, score))

        # Sort by score and take top matches
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        top_nodes = scored_nodes[:max_nodes]

        # Build rich context with relationships
        context = []
        seen_ids = set()

        for node_id, score in top_nodes:
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            data = self.graph.nodes[node_id]
            node_context = {
                "content": data["content"],
                "type": data["node_type"],
                "confidence": data["confidence"],
                "causes": [],
                "caused_by": [],
                "contradicts": [],
                "related": [],
            }

            # Add relationship context
            for _, target, edata in self.graph.out_edges(node_id, data=True):
                edge_type = edata.get("edge_type", "related")
                target_content = self.graph.nodes[target]["content"][:60]
                if edge_type == "causes":
                    node_context["causes"].append(target_content)
                elif edge_type == "contradicts":
                    node_context["contradicts"].append(target_content)
                else:
                    node_context["related"].append(f"--[{edge_type}]--> {target_content}")

            for source, _, edata in self.graph.in_edges(node_id, data=True):
                edge_type = edata.get("edge_type", "related")
                source_content = self.graph.nodes[source]["content"][:60]
                if edge_type == "causes":
                    node_context["caused_by"].append(source_content)
                elif edge_type == "contradicts":
                    node_context["contradicts"].append(source_content)

            context.append(node_context)

        return context

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Get graph statistics."""
        edge_types: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            et = data.get("edge_type", "unknown")
            edge_types[et] = edge_types.get(et, 0) + 1

        node_types: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            nt = data.get("node_type", "unknown")
            node_types[nt] = node_types.get(nt, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
            "connected_components": (
                nx.number_weakly_connected_components(self.graph)
                if self.graph.number_of_nodes() > 0 else 0
            ),
        }
