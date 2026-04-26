"""
Context Builder — assembles the full system prompt for each turn.

Phase 2 upgrade: integrates the knowledge graph, contradictions, and
hypotheses into the system prompt alongside memories, goals, and history.

The key change: instead of flat keyword search, context now includes
causal neighborhoods from the graph.
"""

from __future__ import annotations

from aria.core.identity import build_identity_section
from aria.memory.goal_tracker import GoalTracker
from aria.memory.memory_store import MemoryStore
from aria.memory.session import SessionManager
from aria.models.schemas import Goal, Memory, Turn
from aria.utils.config import MAX_HISTORY_TURNS
from aria.utils.logger import setup_logger
from aria.world.contradictions import ContradictionDetector
from aria.world.graph import KnowledgeGraph
from aria.world.hypotheses import HypothesisEngine

log = setup_logger("aria.context")


class ContextBuilder:
    """Assembles the full system prompt for each cognitive turn."""

    def __init__(
        self,
        memory_store: MemoryStore,
        goal_tracker: GoalTracker,
        session_manager: SessionManager,
        knowledge_graph: KnowledgeGraph | None = None,
        contradiction_detector: ContradictionDetector | None = None,
        hypothesis_engine: HypothesisEngine | None = None,
        tool_registry=None,
        generalization_engine=None,
        skill_loader=None,
    ):
        self.memory = memory_store
        self.goals = goal_tracker
        self.session = session_manager
        self.kg = knowledge_graph
        self.contradictions = contradiction_detector
        self.hypotheses = hypothesis_engine
        self.tool_registry = tool_registry
        self.generalization_engine = generalization_engine
        self.skill_loader = skill_loader

    async def build(self, user_input: str) -> str:
        """
        Build the complete system prompt for a cognitive turn.

        Sections:
          1. Identity — who ARIA is
          2. Knowledge Graph — causal context from the world model
          3. Flat Memories — traditional memory retrieval (still useful)
          4. Active Contradictions — unresolved conflicts
          5. Pending Hypotheses — untested predictions
          6. Goals — active objectives
          7. History — recent conversation turns
          8. Stats — session metrics
        """
        sections: list[str] = []

        # Section 1: Identity
        sections.append(build_identity_section())

        # Section 2: Knowledge Graph context
        if self.kg and self.kg.graph.number_of_nodes() > 0:
            graph_context = await self.kg.retrieve_relevant_context(user_input)
            sections.append(self._format_graph_context(graph_context))

        # Section 3: Flat Memories (backward compat + catches non-graph knowledge)
        memories = await self.memory.retrieve_context(query=user_input)
        sections.append(self._format_memories(memories))

        # Section 4: Active Contradictions
        if self.contradictions:
            unresolved = await self.contradictions.get_unresolved()
            if unresolved:
                sections.append(self._format_contradictions(unresolved))

        # Section 5: Pending Hypotheses
        if self.hypotheses:
            pending = await self.hypotheses.get_pending()
            if pending:
                sections.append(self._format_hypotheses(pending))

        # Section 6: Goals
        goals = await self.goals.get_active()
        sections.append(self._format_goals(goals))

        # Section 7: Recent conversation history
        recent_turns = await self.session.get_recent_turns(limit=MAX_HISTORY_TURNS)
        sections.append(self._format_history(recent_turns))

        # Section 8: Session stats (including graph stats)
        sections.append(await self._format_stats())

        # Section 9: Tools
        if self.tool_registry:
            sections.append("═══════════════════════════════════════════════════════════")
            sections.append(self.tool_registry.get_system_prompt_appendix())
            sections.append("═══════════════════════════════════════════════════════════")

        # Section 10: Universal Principles (Phase 6)
        if self.generalization_engine:
            principles = await self.generalization_engine.get_all_principles()
            if principles:
                sections.append(self.generalization_engine.format_for_prompt(principles))

        # Section 11: Markdown Skills (Phase C)
        if self.skill_loader:
            skill_block = self.skill_loader.format_for_prompt()
            if skill_block:
                sections.append(skill_block)

        full_prompt = "\n".join(sections)
        log.debug(f"Built context: {len(full_prompt)} chars")
        return full_prompt

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def _format_graph_context(self, graph_context: list[dict]) -> str:
        """Format knowledge graph context for the system prompt."""
        lines = [
            "═══════════════════════════════════════════════════════════",
            "YOUR WORLD MODEL (Causal Knowledge Graph)",
            f"({len(graph_context)} relevant knowledge nodes)",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        for i, node in enumerate(graph_context, 1):
            conf = node.get("confidence", 0.5)
            node_type = node.get("type", "fact")
            lines.append(f"  [{i}] ({node_type}) {node['content']}")
            lines.append(f"      confidence: {conf:.1f}")

            if node.get("caused_by"):
                causes = ", ".join(node["caused_by"][:3])
                lines.append(f"      ← caused by: {causes}")

            if node.get("causes"):
                effects = ", ".join(node["causes"][:3])
                lines.append(f"      → causes: {effects}")

            if node.get("contradicts"):
                conflicts = ", ".join(node["contradicts"][:3])
                lines.append(f"      ✗ contradicts: {conflicts}")

            if node.get("related"):
                related = "; ".join(node["related"][:3])
                lines.append(f"      ~ {related}")

            lines.append("")

        return "\n".join(lines)

    def _format_memories(self, memories: list[Memory]) -> str:
        """Format memories for injection into the system prompt."""
        if not memories:
            return (
                "═══════════════════════════════════════════════════════════\n"
                "YOUR MEMORIES\n"
                "═══════════════════════════════════════════════════════════\n\n"
                "You have no memories yet. This is your first interaction. "
                "Everything starts from here.\n"
            )

        lines = [
            "═══════════════════════════════════════════════════════════",
            "YOUR MEMORIES",
            f"({len(memories)} memories loaded)",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        for i, mem in enumerate(memories, 1):
            importance_bar = "█" * int(mem.importance * 10)
            importance_bar = importance_bar.ljust(10, "░")
            tags_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
            lines.append(
                f"  [{i}] {mem.content}\n"
                f"      importance: {importance_bar} {mem.importance:.1f} | "
                f"source: {mem.source} | accessed: {mem.access_count}x{tags_str}"
            )

        lines.append("")
        return "\n".join(lines)

    def _format_contradictions(self, contradictions) -> str:
        """Format unresolved contradictions for the system prompt."""
        lines = [
            "═══════════════════════════════════════════════════════════",
            f"UNRESOLVED CONTRADICTIONS ({len(contradictions)})",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        for i, c in enumerate(contradictions, 1):
            lines.append(f"  [{i}] {c.analysis[:100]}")
            lines.append("")

        return "\n".join(lines)

    def _format_hypotheses(self, hypotheses) -> str:
        """Format pending hypotheses for the system prompt."""
        lines = [
            "═══════════════════════════════════════════════════════════",
            f"PENDING HYPOTHESES ({len(hypotheses)} — check if any can be verified)",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        for i, h in enumerate(hypotheses, 1):
            lines.append(f"  [{i}] {h.claim}")
            lines.append(f"      reasoning: {h.reasoning[:80]}")
            lines.append("")

        return "\n".join(lines)

    def _format_goals(self, goals: list[Goal]) -> str:
        """Format active goals for injection."""
        lines = [
            "═══════════════════════════════════════════════════════════",
            "ACTIVE GOALS",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        if not goals:
            lines.append("  No active goals. Consider what you're working toward.")
        else:
            for i, goal in enumerate(goals, 1):
                priority_icon = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(goal.priority.value, "⚪")
                lines.append(
                    f"  {priority_icon} [{goal.priority.value.upper()}] {goal.description}"
                )

        lines.append("")
        return "\n".join(lines)

    def _format_history(self, turns: list[Turn]) -> str:
        """Format recent conversation history."""
        lines = [
            "═══════════════════════════════════════════════════════════",
            "RECENT CONVERSATION",
            "═══════════════════════════════════════════════════════════",
            "",
        ]

        if not turns:
            lines.append("  No conversation history in this session yet.")
        else:
            for turn in turns:
                user_msg = turn.user_input[:200]
                aria_msg = turn.response[:300]
                lines.append(f"  Turn {turn.turn_number}:")
                lines.append(f"    Human: {user_msg}")
                lines.append(f"    ARIA:  {aria_msg}")
                lines.append("")

        lines.append("")
        return "\n".join(lines)

    async def _format_stats(self) -> str:
        """Format session statistics including graph stats."""
        session = self.session.current
        total_memories = await self.memory.count()
        active_goals = await self.goals.count_active()
        total_turns = await self.session.get_total_turns()

        turn_count = session.turn_count if session else 0
        avg_conf = session.avg_confidence if session else 0.0
        session_id = session.id[:8] if session else "none"

        # Graph stats
        graph_nodes = 0
        graph_edges = 0
        if self.kg:
            stats = self.kg.stats()
            graph_nodes = stats["total_nodes"]
            graph_edges = stats["total_edges"]

        return (
            "═══════════════════════════════════════════════════════════\n"
            "SESSION STATUS\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"  Session:        {session_id}...\n"
            f"  Turn:           {turn_count}\n"
            f"  Total turns:    {total_turns} (all sessions)\n"
            f"  Memories:       {total_memories}\n"
            f"  Knowledge:      {graph_nodes} nodes, {graph_edges} edges\n"
            f"  Active goals:   {active_goals}\n"
            f"  Avg confidence: {avg_conf:.2f}\n"
        )
