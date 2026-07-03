import pytest
from unittest.mock import patch

from silex.core.skills import SkillLoader
from silex.memory.vector_store import VectorStore
from silex.mcp.filter import ToolsetFilter
from silex.mcp.config import _expand_env
from silex.plugins.registry import KronosRegistry


@pytest.mark.asyncio
async def test_semantic_skill_retrieval(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    (skills_dir / "docker_guide.md").write_text(
        "Instruction on how to run Docker containers, build images, and prune volumes.",
        encoding="utf-8",
    )
    (skills_dir / "kubernetes_tips.md").write_text(
        "Advanced workflows for deploying pods, configuring ingresses, and autoscaling services in K8s.",
        encoding="utf-8",
    )
    (skills_dir / "python_clean_code.md").write_text(
        "Principles for writing clean Python code, static type-checking, and using pytest.",
        encoding="utf-8",
    )

    vector_path = tmp_path / "vector_db"

    with patch("silex.core.skills.KRONOS_SKILLS", skills_dir), patch(
        "silex.utils.config.SILEX_VECTOR_DB", vector_path
    ):
        vs = VectorStore(collection_name="test_skills_collection")
        loader = SkillLoader(vector_store=vs)

        count = loader.load_all()
        assert count == 3
        assert len(loader.skills) == 3

        relevant_docker = loader.get_relevant_skills("how do I prune docker containers?", limit=1)
        assert len(relevant_docker) == 1
        assert "docker_guide" in relevant_docker

        relevant_k8s = loader.get_relevant_skills("kubernetes ingress configuration", limit=1)
        assert len(relevant_k8s) == 1
        assert "kubernetes_tips" in relevant_k8s

        relevant_python = loader.get_relevant_skills("writing clean pytest code in python", limit=1)
        assert len(relevant_python) == 1
        assert "python_clean_code" in relevant_python


def test_format_index_for_prompt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "tell_joke.md").write_text("# Tell Joke\nDo the thing.", encoding="utf-8")
    (skills_dir / "tell_joke.yaml").write_text(
        "name: tell_joke\ndescription: Jokes\ntrigger: joke humor\n", encoding="utf-8"
    )

    with patch("silex.core.skills.KRONOS_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        index = loader.format_index_for_prompt()
        assert "SKILLS INDEX" in index
        assert "tell_joke" in index
        assert "skill_view" in index
        assert "<skill name=" not in index


def test_inline_skill_in_prompt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "repo_onboard.md").write_text(
        "---\nname: repo_onboard\ninline: true\n---\n# Onboard\nSteps here.",
        encoding="utf-8",
    )

    with patch("silex.core.skills.KRONOS_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        prompt = loader.format_for_prompt("onboard repo")
        assert "<skill name=\"repo_onboard\">" in prompt
        assert "Steps here" in prompt


@pytest.mark.asyncio
async def test_skill_view_tool(tmp_path):
    from silex.tools.skills import SkillViewTool

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "demo.md").write_text("# Demo skill body", encoding="utf-8")

    with patch("silex.core.skills.KRONOS_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        tool = SkillViewTool(loader)
        result = await tool.execute(name="demo")
        assert "Demo skill body" in result


def test_toolset_filter():
    tools = [{"name": "read_file"}, {"name": "write_file"}, {"name": "list_directory"}]
    filt = ToolsetFilter(allowed_tools=["read_file", "list_directory"])
    out = filt.filter_tools(tools)
    assert [t["name"] for t in out] == ["read_file", "list_directory"]


def test_mcp_env_expand():
    with patch.dict("os.environ", {"MY_TOKEN": "secret123"}):
        assert _expand_env("Bearer ${MY_TOKEN}") == "Bearer secret123"


def test_install_bundled_skill(tmp_path, monkeypatch):
    project_root = tmp_path / "proj"
    skills = project_root / "skills"
    skills.mkdir(parents=True)
    (skills / "tell_joke.md").write_text("# joke", encoding="utf-8")

    kronos_skills = tmp_path / "home" / "skills"
    registry_dir = tmp_path / "home" / "registry"
    registry_dir.mkdir(parents=True)

    monkeypatch.setattr("silex.utils.config.PROJECT_ROOT", project_root)
    monkeypatch.setattr("silex.utils.config.KRONOS_SKILLS", kronos_skills)
    monkeypatch.setattr("silex.utils.config.KRONOS_HOME", tmp_path / "home")

    reg = KronosRegistry()
    reg.registry_dir = registry_dir
    reg.catalog_path = registry_dir / "catalog.yaml"
    ok, msg = reg.install_bundled("tell_joke")
    assert ok
    assert (kronos_skills / "tell_joke.md").exists()


def test_mcp_adapter_tool_naming():
    from silex.mcp.adapter import McpToolAdapter

    async def _noop(*a, **k):
        return "ok"

    tool = McpToolAdapter("filesystem", "read_file", "Read a file", {}, _noop)
    assert tool.name == "mcp__filesystem__read_file"
