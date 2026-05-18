import pytest
from unittest.mock import patch, MagicMock
from aria.core.skills import SkillLoader
from aria.memory.vector_store import VectorStore

@pytest.mark.asyncio
async def test_semantic_skill_retrieval(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    
    # Create mock skill files
    (skills_dir / "docker_guide.md").write_text("Instruction on how to run Docker containers, build images, and prune volumes.", encoding="utf-8")
    (skills_dir / "kubernetes_tips.md").write_text("Advanced workflows for deploying pods, configuring ingresses, and autoscaling services in K8s.", encoding="utf-8")
    (skills_dir / "python_clean_code.md").write_text("Principles for writing clean Python code, static type-checking, and using pytest.", encoding="utf-8")

    vector_path = tmp_path / "vector_db"
    
    with patch("aria.core.skills.VYN_SKILLS", skills_dir), patch("aria.utils.config.VYN_VECTOR_DB", vector_path):
        vs = VectorStore(collection_name="test_skills_collection")
        loader = SkillLoader(vector_store=vs)
        
        # Load and Index
        count = loader.load_all()
        assert count == 3
        assert len(loader.skills) == 3

        # Semantic Query 1: Docker
        relevant_docker = loader.get_relevant_skills("how do I prune docker containers?", limit=1)
        assert len(relevant_docker) == 1
        assert "docker_guide" in relevant_docker

        # Semantic Query 2: K8s / Kubernetes
        relevant_k8s = loader.get_relevant_skills("kubernetes ingress configuration", limit=1)
        assert len(relevant_k8s) == 1
        assert "kubernetes_tips" in relevant_k8s

        # Semantic Query 3: Python
        relevant_python = loader.get_relevant_skills("writing clean pytest code in python", limit=1)
        assert len(relevant_python) == 1
        assert "python_clean_code" in relevant_python

        # Check prompt formatting
        formatted = loader.format_for_prompt("Docker")
        assert "<skill name=\"docker_guide\">" in formatted
        assert "</skill>" in formatted
