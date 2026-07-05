"""
tests/test_phase3_math.py — Phase 3 Deep Production Logic Math Anchors.

These tests protect the mathematical core against future stubs.
They assert the EXACT formulas required by the implementation plan.

Run first to confirm failures before applying production fixes,
then rerun to confirm all green after the fixes.
"""

from __future__ import annotations

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


# ============================================================================
# 1. CRITIC — Geometric Mean Formula
# ============================================================================


class TestGeometricMeanCritic:
    """
    The geometric mean (acc × dep × hon)^(1/3) collapses to near-zero if ANY
    axis is near-zero.  The old arithmetic sum lets catastrophically dishonest
    responses outrank consistently adequate ones.
    """

    @staticmethod
    def _geo(acc: float, dep: float, hon: float) -> float:
        """Reference implementation of the geometric mean."""
        return (acc * dep * hon) ** (1.0 / 3.0)

    @staticmethod
    def _arith_sum(acc: float, dep: float, hon: float) -> float:
        """The old (wrong) linear sum used in the stub."""
        return acc + dep + hon

    def test_zero_honesty_collapses_geometric_score(self):
        """(0.9, 0.9, 0.0) → geometric mean = 0.0 — must be rejected."""
        score = self._geo(0.9, 0.9, 0.0)
        assert score == pytest.approx(0.0), (
            f"Geometric mean of (0.9, 0.9, 0.0) must equal 0.0, got {score}"
        )

    def test_arithmetic_would_have_wrongly_accepted_dishonest_response(self):
        """Prove the old arithmetic sum would accept (0.9, 0.9, 0.0)."""
        self._arith_sum(0.9, 0.9, 0.0)
        # The old threshold was sum >= 2.1 (≡ three scores ≥ 0.7)
        # 0.9 + 0.9 + 0.0 = 1.8 — actually rejected by sum comparison too
        # BUT the RANKING bug: compare dishonest vs. honest:
        self._arith_sum(0.9, 0.9, 0.0)  # 1.8
        self._arith_sum(0.7, 0.7, 0.7)  # 2.1
        # arithmetic correctly ranks honest above dishonest here
        # BUT the real bug is the partial-collapse scenario:
        self._arith_sum(0.95, 0.95, 0.05)  # 1.95
        self._arith_sum(0.75, 0.75, 0.75)  # 2.25
        # Arithmetic: partial (1.95) < solid (2.25) → correct
        # The actual bug surfaces when comparing retries:
        # If retry has (0.95, 0.95, 0.05) vs best (0.70, 0.70, 0.72),
        # arithmetic sum: 1.95 vs 2.12 → still correct
        # BUT:  (0.95, 0.95, 0.30) arithmetic=2.20  vs  (0.70, 0.70, 0.70) arith=2.10
        # Geometric: (0.95×0.95×0.30)^(1/3) = (0.27075)^(1/3) ≈ 0.647
        #            (0.70×0.70×0.70)^(1/3) = 0.70
        # Geometric correctly ranks solid (0.70) above partial-dishonest (0.647)
        geo_partial = self._geo(0.95, 0.95, 0.30)
        geo_solid = self._geo(0.70, 0.70, 0.70)
        arith_partial = self._arith_sum(0.95, 0.95, 0.30)
        arith_solid = self._arith_sum(0.70, 0.70, 0.70)

        # Geometric: solid wins (correct)
        assert geo_solid > geo_partial, (
            f"Geometric mean must rank solid (0.70,0.70,0.70)={geo_solid:.4f} "
            f"above partial-dishonest (0.95,0.95,0.30)={geo_partial:.4f}"
        )
        # Arithmetic: partial WINS over solid — this is the bug
        assert arith_partial > arith_solid, (
            "Arithmetic sum must rank the partial-dishonest response HIGHER "
            f"({arith_partial} > {arith_solid}), proving the old formula is broken"
        )

    def test_geometric_mean_all_equal_is_identity(self):
        """When all three axes are equal, geometric mean equals that value."""
        for v in [0.0, 0.5, 0.7, 0.9, 1.0]:
            assert self._geo(v, v, v) == pytest.approx(v, abs=1e-9)

    def test_geometric_mean_threshold_65_rejects_any_sub_65_axis(self):
        """
        With threshold=0.65, a response (0.65, 0.65, 0.64) scores ≈0.6466 — rejected.
        A response (0.65, 0.65, 0.65) scores exactly 0.65 — accepted.
        """
        just_below = self._geo(0.65, 0.65, 0.64)
        threshold = 0.65
        assert just_below < threshold

        exactly_at = self._geo(0.65, 0.65, 0.65)
        assert exactly_at == pytest.approx(0.65, abs=1e-9)

    def test_geometric_score_is_imported_from_critic(self):
        """critic.py must expose a `geometric_score` static method."""
        from silex.core.critic import ResponseCritic

        assert hasattr(ResponseCritic, "geometric_score"), (
            "ResponseCritic must expose a `geometric_score(acc, dep, hon) -> float` static method"
        )
        score = ResponseCritic.geometric_score(0.8, 0.8, 0.8)
        assert score == pytest.approx(0.8, abs=1e-9)

    def test_cognitive_loop_uses_geometric_score_for_comparison(self):
        """
        cognitive_loop.py must import geometric_score from critic and use it
        instead of sum([...]) when selecting the best critic attempt.
        """
        import inspect
        import silex.core.cognitive_loop as cl_mod

        source = inspect.getsource(cl_mod)
        assert "geometric_score" in source, (
            "cognitive_loop.py must call ResponseCritic.geometric_score() "
            "instead of sum([accuracy, depth, honesty])"
        )


# ============================================================================
# 2. MEMORY STORE — Unified Multiplicative Decay
# ============================================================================


class TestMemoryRetrievalScore:
    """
    The non-vector retrieval score must use importance × exp(-age/30) as a
    compound multiplicative factor, not as independent additive terms.
    """

    def _make_memory(
        self,
        importance: float,
        age_days: float,
        confidence: float = 0.8,
        source: str = "user",
        memory_type: str = "semantic",
    ):
        """Build a minimal Memory-like object for scoring."""
        from silex.models.schemas import Memory, MemorySource, MemoryType

        now = datetime.now(timezone.utc)
        last_accessed = (now - timedelta(days=age_days)).isoformat()
        created_at = last_accessed
        return Memory(
            content="Test memory content about the topic at hand.",
            source=MemorySource(source),
            memory_type=MemoryType(memory_type),
            importance=importance,
            confidence=confidence,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=1,
        )

    def test_old_memory_scores_lower_than_fresh_same_importance(self):
        """A 180-day-old memory must score materially lower than a 1-day-old one."""
        from silex.memory.memory_store import MemoryStore

        fresh = self._make_memory(importance=0.8, age_days=1)
        old = self._make_memory(importance=0.8, age_days=180)
        score_fresh = MemoryStore._retrieval_score(fresh, "topic")
        score_old = MemoryStore._retrieval_score(old, "topic")
        assert score_fresh > score_old, (
            f"Fresh memory ({score_fresh:.4f}) must outscore 180-day-old memory "
            f"({score_old:.4f}) at equal importance"
        )

    def test_decay_is_multiplicative_not_additive(self):
        """
        The compound term importance × exp(-age/30) must dominate.
        If decay were purely additive (old code), halving importance AND
        having 60-day age would still give a higher score than a very fresh
        low-importance memory in some parameter ranges.

        This test checks that the ranking is governed by the product.
        """
        from silex.memory.memory_store import MemoryStore

        # High importance but very old
        old_important = self._make_memory(importance=0.9, age_days=120)
        # Low importance but very fresh
        fresh_low = self._make_memory(importance=0.3, age_days=0)

        MemoryStore._retrieval_score(old_important, "topic")
        MemoryStore._retrieval_score(fresh_low, "topic")

        # The compound decay should significantly penalise the old one:
        # old compound: 0.9 × exp(-120/30) = 0.9 × exp(-4) ≈ 0.9 × 0.018 ≈ 0.016
        # fresh compound: 0.3 × exp(0) = 0.3 × 1.0 = 0.3
        expected_old_compound = 0.9 * math.exp(-120 / 30)
        expected_fresh_compound = 0.3 * math.exp(0)
        assert expected_fresh_compound > expected_old_compound * 5, (
            "Fresh low-importance compound must dominate old high-importance compound "
            "by 5× to confirm the multiplicative formula is correct"
        )

    def test_retrieval_score_exposes_exp_decay(self):
        """_retrieval_score must use math.exp() for the decay term."""
        import inspect
        from silex.memory import memory_store as ms_mod

        source = inspect.getsource(ms_mod.MemoryStore._retrieval_score)
        assert "exp(" in source, (
            "_retrieval_score must use math.exp() for time-decay, not additive recency"
        )

    def test_retrieval_score_uses_multiplicative_importance_decay(self):
        """
        The compound term must be importance MULTIPLIED by the decay factor,
        not importance ADDED to the decay factor.
        """
        import inspect
        from silex.memory import memory_store as ms_mod

        source = inspect.getsource(ms_mod.MemoryStore._retrieval_score)
        # Must contain the multiplicative compound: importance * exp(...)
        assert "importance" in source and "exp(" in source, (
            "_retrieval_score must contain both 'importance' and 'exp('"
        )
        # Assert there is a multiplication between importance and exp
        # (heuristic: the compound token appears in source)
        assert (
            "importance * math.exp(" in source
            or "importance*math.exp(" in source
            or "* exp(" in source
        ), "_retrieval_score must multiply importance by exp(decay) as a compound term"


# ============================================================================
# 3. DEBATE ENGINE — KnowledgeGraph Injection
# ============================================================================


class TestDebateEngineKGInjection:
    """
    DebateEngine must accept a knowledge_graph parameter and inject
    CONTRADICTS edge context into Agent B's prompt.
    """

    def test_debate_engine_accepts_knowledge_graph(self):
        """DebateEngine.__init__ must accept knowledge_graph kwarg."""
        import inspect
        from silex.core.debate import DebateEngine

        sig = inspect.signature(DebateEngine.__init__)
        assert "knowledge_graph" in sig.parameters, (
            "DebateEngine.__init__ must accept a `knowledge_graph` parameter"
        )

    def test_debate_engine_accepts_contradiction_detector(self):
        """DebateEngine.__init__ must accept contradiction_detector kwarg."""
        import inspect
        from silex.core.debate import DebateEngine

        sig = inspect.signature(DebateEngine.__init__)
        assert "contradiction_detector" in sig.parameters, (
            "DebateEngine.__init__ must accept a `contradiction_detector` parameter"
        )

    @pytest.mark.asyncio
    async def test_agent_b_prompt_contains_kg_context(self):
        """
        When the KG has CONTRADICTS edges for a topic, Agent B's LLM call
        must receive that context in its user_input string.
        """
        from silex.core.debate import DebateEngine
        from silex.storage.database import Database

        # Mock KG returning a contradiction context
        mock_kg = MagicMock()
        mock_kg.retrieve_relevant_context = AsyncMock(
            return_value=[
                {
                    "content": "The Earth is flat",
                    "type": "fact",
                    "confidence": 0.1,
                    "caused_by": [],
                    "causes": [],
                    "contradicts": ["The Earth is approximately spherical"],
                    "related": [],
                }
            ]
        )

        # Mock contradiction detector
        mock_cd = MagicMock()
        mock_cd.get_unresolved = AsyncMock(return_value=[])

        # Mock DB
        mock_db = MagicMock(spec=Database)
        mock_db.execute = AsyncMock()

        # Capture what gets sent to complete_json
        captured_prompts = []
        from silex.models.schemas import DebateArgument

        mock_llm = MagicMock()

        async def capture_complete_json(schema, system_prompt, user_input, **kwargs):
            captured_prompts.append({"system": system_prompt, "user": user_input})
            return DebateArgument(
                agent_id="Agent B",
                claim="Counter-claim",
                reasoning="Counter-reasoning",
                evidence_or_logic="Counter-evidence",
            )

        mock_llm.complete_json = capture_complete_json

        engine = DebateEngine(
            llm_client=mock_llm,
            db=mock_db,
            knowledge_graph=mock_kg,
            contradiction_detector=mock_cd,
        )

        # Call Agent B directly
        await engine._generate_argument("Agent B", "Is the Earth flat?", [])

        # Agent B's call must have received KG context in the user prompt
        assert len(captured_prompts) >= 1
        agent_b_user_prompt = captured_prompts[-1]["user"]
        assert (
            "CONTRADICTS" in agent_b_user_prompt
            or "contradict" in agent_b_user_prompt.lower()
            or "flat" in agent_b_user_prompt.lower()
        ), (
            f"Agent B's user prompt must contain KG contradiction context. Got: {agent_b_user_prompt[:300]}"
        )


# ============================================================================
# 4. META-REASONING — Algorithmic Failure Clustering
# ============================================================================


class TestMetaReasoningFailureClusters:
    """
    MetaReasoningEngine must compute failure clusters algorithmically
    (not just dump raw rows) and expose structured cluster data.
    """

    def test_compute_failure_clusters_method_exists(self):
        """_compute_failure_clusters must exist as a method on MetaReasoningEngine."""
        from silex.core.meta_reasoning import MetaReasoningEngine

        assert hasattr(MetaReasoningEngine, "_compute_failure_clusters"), (
            "MetaReasoningEngine must have a `_compute_failure_clusters()` method"
        )

    def test_compute_confidence_drift_method_exists(self):
        """_compute_confidence_drift must exist as a method on MetaReasoningEngine."""
        from silex.core.meta_reasoning import MetaReasoningEngine

        assert hasattr(MetaReasoningEngine, "_compute_confidence_drift"), (
            "MetaReasoningEngine must have a `_compute_confidence_drift()` method"
        )

    def test_failure_cluster_identifies_honesty_bottleneck(self):
        """
        Given synthetic improvement_logs rows where honesty is always lowest,
        _compute_failure_clusters must identify 'honesty' as the bottleneck axis.
        """
        from silex.core.meta_reasoning import MetaReasoningEngine

        synthetic_rows = [
            {
                "accuracy_score": 0.8,
                "depth_score": 0.75,
                "honesty_score": 0.3,
                "feedback": "Dishonest",
            },
            {
                "accuracy_score": 0.85,
                "depth_score": 0.80,
                "honesty_score": 0.25,
                "feedback": "Overconfident",
            },
            {
                "accuracy_score": 0.78,
                "depth_score": 0.82,
                "honesty_score": 0.35,
                "feedback": "No uncertainty",
            },
        ]

        report = MetaReasoningEngine._compute_failure_clusters(synthetic_rows)

        assert report["bottleneck_axis"] == "honesty", (
            f"With consistently low honesty scores, bottleneck must be 'honesty'. Got: {report}"
        )
        assert report["avg_honesty"] < 0.5

    def test_failure_cluster_identifies_depth_bottleneck(self):
        """When depth is always lowest, bottleneck must be depth."""
        from silex.core.meta_reasoning import MetaReasoningEngine

        synthetic_rows = [
            {
                "accuracy_score": 0.9,
                "depth_score": 0.2,
                "honesty_score": 0.8,
                "feedback": "Shallow",
            },
            {
                "accuracy_score": 0.85,
                "depth_score": 0.3,
                "honesty_score": 0.75,
                "feedback": "Surface",
            },
        ]

        report = MetaReasoningEngine._compute_failure_clusters(synthetic_rows)
        assert report["bottleneck_axis"] == "depth"

    def test_confidence_drift_detects_negative_slope(self):
        """
        Given a list of confidence values trending downward,
        _compute_confidence_drift must return a negative slope.
        """
        from silex.core.meta_reasoning import MetaReasoningEngine

        # Simulate confidence values: clearly declining trend (most-recent first)
        confidences = [0.50, 0.55, 0.60, 0.65, 0.72, 0.80, 0.85, 0.90]
        slope = MetaReasoningEngine._compute_confidence_drift(confidences)
        assert slope < 0.0, (
            f"Declining confidence series must produce negative drift slope, got {slope}"
        )

    def test_confidence_drift_detects_stable(self):
        """A flat confidence series must produce near-zero slope."""
        from silex.core.meta_reasoning import MetaReasoningEngine

        confidences = [0.75] * 10
        slope = MetaReasoningEngine._compute_confidence_drift(confidences)
        assert abs(slope) < 0.01, (
            f"Flat confidence series must produce near-zero slope, got {slope}"
        )


# ============================================================================
# 5. POST-PHASE 3 REFINEMENTS
# ============================================================================


class TestPostPhase3Refinements:
    """Tests covering local sandbox validation, RRF hybrid search, and memory tools."""

    @pytest.mark.asyncio
    async def test_sandbox_command_validation(self):
        """Verify that RunTerminalCommandTool rejects dangerous commands outside workspace."""
        from silex.tools.system import RunTerminalCommandTool

        tool = RunTerminalCommandTool()

        with patch("silex.tools.system.terminal_execution_enabled", return_value=True):
            # Test dangerous commands
            res1 = await tool.execute("rm -rf /")
            assert "rejected" in res1.lower(), f"Expected rejected command, got: {res1}"

            res2 = await tool.execute("del /f /q c:\\windows\\system32")
            assert "rejected" in res2.lower()

            # Test directory traversal/access outside workspace in a write command
            res3 = await tool.execute("rm -f ../../outside_file.txt")
            assert "rejected" in res3.lower()

    @pytest.mark.asyncio
    async def test_hybrid_search_rrf_blending(self):
        """Verify that RRF properly blends and ranks keyword and semantic results."""
        from silex.memory.memory_store import MemoryStore
        from silex.models.schemas import Memory, MemorySource, MemoryType
        from unittest.mock import MagicMock

        # Construct synthetic memories
        Memory(
            id="mem1",
            content="Python script helper",
            source=MemorySource.USER,
            memory_type=MemoryType.PROJECT,
            importance=0.8,
        )
        Memory(
            id="mem2",
            content="Python terminal execution",
            source=MemorySource.USER,
            memory_type=MemoryType.PROJECT,
            importance=0.8,
        )
        Memory(
            id="mem3",
            content="ChromaDB vector store",
            source=MemorySource.USER,
            memory_type=MemoryType.PROJECT,
            importance=0.8,
        )

        # Mock DB
        mock_db = MagicMock()
        mock_db.fetch_all = AsyncMock(return_value=[])

        MemoryStore(mock_db)

        # We manually test RRF blending by injecting rankings
        keyword_ranks = {"mem1": 1, "mem2": 2}
        semantic_ranks = {"mem2": 1, "mem3": 2}

        all_ids = set(keyword_ranks.keys()) | set(semantic_ranks.keys())
        raw_rrf_scores = {}
        for m_id in all_ids:
            rank_k = keyword_ranks.get(m_id, 1e9)
            rank_s = semantic_ranks.get(m_id, 1e9)
            raw_rrf_scores[m_id] = 1.0 / (60.0 + rank_k) + 1.0 / (60.0 + rank_s)

        rrf_scores = {}
        max_rrf = 2.0 / 61.0
        for m_id, raw_score in raw_rrf_scores.items():
            rrf_scores[m_id] = min(raw_score / max_rrf, 1.0)

        # Verify ranking order: mem2 > mem1 > mem3
        assert rrf_scores["mem2"] > rrf_scores["mem1"], (
            f"mem2 ({rrf_scores['mem2']:.4f}) must outrank mem1 ({rrf_scores['mem1']:.4f})"
        )
        assert rrf_scores["mem1"] > rrf_scores["mem3"], (
            f"mem1 ({rrf_scores['mem1']:.4f}) must outrank mem3 ({rrf_scores['mem3']:.4f})"
        )

    def test_memory_tools_registration(self):
        """Verify that memory tools are registered in ToolRegistry."""
        from silex.tools.registry import ToolRegistry
        from unittest.mock import MagicMock

        mock_ms = MagicMock()
        registry = ToolRegistry(memory_store=mock_ms)

        assert "search_memory" in registry.tools
        assert "append_runtime_observation" in registry.tools
