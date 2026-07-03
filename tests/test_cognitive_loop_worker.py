import pytest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock
from silex.core.cognitive_loop import CognitiveLoop
from silex.tools.worker import SpawnWorkerTool
from agent.jobs import WorkerJobResult
from agent.security.lease import ActuationLease

# Source modules to patch for __init__ test
MOCKS = [
    "silex.storage.database.Database",
    "silex.llm.factory.build_provider",
    "silex.llm.router.ModelRouter",
    "silex.world.graph.KnowledgeGraph",
    "silex.world.contradictions.ContradictionDetector",
    "silex.world.hypotheses.HypothesisEngine",
    "silex.core.causal_graph.CausalKnowledgeGraphGenerator",
    "silex.security.trust_engine.BayesianTrustEngine",
    "silex.memory.vector_store.VectorStore",
    "silex.memory.pruner.ContextPruner",
    "silex.tools.registry.ToolRegistry",
    "silex.core.generalization.GeneralizationEngine",
    "silex.core.skills.SkillLoader",
    "silex.core.creativity.CreativityStack",
    "silex.knowledge_graph.ontology.Ontology",
    "silex.core.semantic_parser.SemanticParser",
    "silex.core.context_builder.ContextBuilder",
    "silex.core.critic.ResponseCritic",
    "silex.core.improver.ImprovementLogger",
    "silex.core.debate.DebateEngine",
    "silex.memory.memory_store.MemoryStore",
    "silex.memory.goal_tracker.GoalTracker",
    "silex.memory.session.SessionManager"
]

@pytest.mark.asyncio
async def test_cognitive_loop_orchestrator_initialization():
    """Verify that CognitiveLoop initializes the worker orchestrator."""
    with ExitStack() as stack:
        for m in MOCKS:
            stack.enter_context(patch(m))
        
        loop = CognitiveLoop()
        assert loop.worker_orchestrator is not None
        assert loop.worker_orchestrator.max_workers == 4

@pytest.mark.asyncio
async def test_delegate_to_workers():
    """Test delegate_to_workers issues leases and calls spawn_job."""
    loop = CognitiveLoop.__new__(CognitiveLoop)
    loop.session = SimpleNamespace(current=SimpleNamespace(id="test_session_123", turn_count=0))
    loop.worker_orchestrator = MagicMock()
    
    mock_handle = AsyncMock()
    mock_handle.result.return_value = "worker output response"
    loop.worker_orchestrator.spawn_job = AsyncMock(return_value=mock_handle)
    
    subtasks = [
        {"task": "echo 'hello'", "tools_allowed": ["run_terminal_command"], "timeout_seconds": 300}
    ]
    
    results = await loop.delegate_to_workers(subtasks)
    assert results == ["worker output response"]
    
    loop.worker_orchestrator.spawn_job.assert_called_once()
    job_arg, lease_arg = loop.worker_orchestrator.spawn_job.call_args[0]
    assert job_arg.command == "echo 'hello'"
    assert job_arg.allowed_tools == ["run_terminal_command"]
    assert isinstance(lease_arg, ActuationLease)
    assert lease_arg.agent_id == "test_session_123"

@pytest.mark.asyncio
async def test_spawn_worker_tool():
    """Test SpawnWorkerTool execute method."""
    tool = SpawnWorkerTool()
    assert tool.name == "spawn_worker"
    assert tool.risk_level == "sandbox_write"
    assert tool.requires_approval is True
    
    mock_handle = AsyncMock()
    mock_handle.structured_result.return_value = WorkerJobResult(
        job_id="job_test",
        worker_id="worker_test",
        success=True,
        exit_code=0,
        output="success output",
    )
    
    with patch("agent.orchestrator.WorkerOrchestrator.instance") as mock_orchestrator_instance:
        mock_orchestrator = MagicMock()
        mock_orchestrator.spawn_job = AsyncMock(return_value=mock_handle)
        mock_orchestrator_instance.return_value = mock_orchestrator
        
        output = await tool.execute(task="ls", tools_allowed=["run_terminal_command"], timeout_seconds=120)
        assert output == "success output"
        mock_orchestrator.spawn_job.assert_called_once()
