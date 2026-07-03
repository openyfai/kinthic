"""
agent package for Kronos Agent Orchestration.
Defines parallel worker isolation, orchestration layer, and security guards.
"""

from agent.orchestrator import WorkerOrchestrator

__all__ = ["WorkerOrchestrator"]
