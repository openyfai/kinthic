import pytest
from pathlib import Path
from unittest.mock import patch

from silex.core.skills import SkillLoader
from silex.memory.vector_store import VectorStore
from silex.mcp.filter import ToolsetFilter
from silex.mcp.config import _expand_env
from silex.plugins.registry import KinthicRegistry


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

    with (
        patch("silex.core.skills.KINTHIC_SKILLS", skills_dir),
        patch("silex.utils.config.SILEX_VECTOR_DB", vector_path),
    ):
        vs = VectorStore(collection_name="test_skills_collection")
        loader = SkillLoader(vector_store=vs)

        count = loader.load_all()
        assert count == 3
        assert len(loader.skills) == 3

        relevant_docker = loader.get_relevant_skills(
            "how do I prune docker containers?", limit=1
        )
        assert len(relevant_docker) == 1
        assert "docker_guide" in relevant_docker

        relevant_k8s = loader.get_relevant_skills(
            "kubernetes ingress configuration", limit=1
        )
        assert len(relevant_k8s) == 1
        assert "kubernetes_tips" in relevant_k8s

        relevant_python = loader.get_relevant_skills(
            "writing clean pytest code in python", limit=1
        )
        assert len(relevant_python) == 1
        assert "python_clean_code" in relevant_python


def test_format_index_for_prompt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "tell_joke.md").write_text(
        "# Tell Joke\nDo the thing.", encoding="utf-8"
    )
    (skills_dir / "tell_joke.yaml").write_text(
        "name: tell_joke\ndescription: Jokes\ntrigger: joke humor\n", encoding="utf-8"
    )

    with patch("silex.core.skills.KINTHIC_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        index = loader.format_index_for_prompt()
        assert "SKILLS INDEX" in index
        assert "tell_joke" in index
        assert "skill_view" in index
        assert "<skill name=" not in index


def test_flat_skill_defaults_to_community_trust(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "unknown_skill.md").write_text(
        "# Unknown\nUser dropped this file.", encoding="utf-8"
    )

    with patch("silex.core.skills.KINTHIC_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        assert loader.skill_meta["unknown_skill"].trust_level == "community"
        assert loader.skill_meta["unknown_skill"].source == "user"


def test_inline_skill_in_prompt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "repo_onboard.md").write_text(
        "---\nname: repo_onboard\ninline: true\n---\n# Onboard\nSteps here.",
        encoding="utf-8",
    )

    with patch("silex.core.skills.KINTHIC_SKILLS", skills_dir):
        loader = SkillLoader()
        loader.load_all()
        prompt = loader.format_for_prompt("onboard repo")
        assert '<skill name="repo_onboard">' in prompt
        assert "Steps here" in prompt


@pytest.mark.asyncio
async def test_skill_view_tool(tmp_path):
    from silex.tools.skills import SkillViewTool

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "demo.md").write_text("# Demo skill body", encoding="utf-8")

    with patch("silex.core.skills.KINTHIC_SKILLS", skills_dir):
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

    kinthic_skills = tmp_path / "home" / "skills"
    registry_dir = tmp_path / "home" / "registry"
    registry_dir.mkdir(parents=True)

    monkeypatch.setattr("silex.utils.config.PROJECT_ROOT", project_root)
    monkeypatch.setattr("silex.utils.config.KINTHIC_SKILLS", kinthic_skills)
    monkeypatch.setattr("silex.utils.config.KINTHIC_HOME", tmp_path / "home")

    reg = KinthicRegistry()
    reg.registry_dir = registry_dir
    reg.catalog_path = registry_dir / "catalog.yaml"
    ok, msg = reg.install_bundled("tell_joke")
    assert ok
    assert (kinthic_skills / "tell_joke.md").exists()


@pytest.mark.asyncio
async def test_skill_manage_reload_roundtrip(tmp_path):
    from silex.tools.skills import SkillManageTool

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    kinthic_home = tmp_path / "home"

    with (
        patch("silex.core.skills.KINTHIC_SKILLS", skills_dir),
        patch("silex.utils.config.KINTHIC_HOME", kinthic_home),
        patch("silex.utils.config.KINTHIC_SKILLS", skills_dir),
    ):
        loader = SkillLoader()
        loader.load_all()
        tool = SkillManageTool(loader)
        content = "---\nname: new_skill\nsource: user\n---\n# New Skill\nDo the thing."
        result = await tool.execute(name="new_skill", content=content)
        assert "Success" in result
        assert "new_skill" in loader.skills
        assert loader.get_skill_body("new_skill") is not None


def test_mcp_adapter_tool_naming():
    from silex.mcp.adapter import McpToolAdapter

    async def _noop(*a, **k):
        return "ok"

    tool = McpToolAdapter("filesystem", "read_file", "Read a file", {}, _noop)
    assert tool.name == "mcp__filesystem__read_file"


def test_skill_manage_requires_approval_flags():
    from silex.tools.skills import SkillManageTool

    assert SkillManageTool.requires_approval is True
    assert SkillManageTool.risk_level == "repo_write"


@pytest.mark.asyncio
async def test_skill_manage_blocked_without_approval():
    import json
    from unittest.mock import patch

    from silex.models.schemas import ToolCall
    from silex.tools.registry import ToolRegistry
    from silex.tools.skills import SkillManageTool

    registry = ToolRegistry()
    registry.tools = {}
    registry.register(SkillManageTool())

    with patch("silex.tools.registry.require_tool_approvals", return_value=True):
        result = await registry.execute(
            ToolCall(
                tool_name="skill_manage",
                arguments=json.dumps(
                    {
                        "name": "test_skill",
                        "content": "---\nname: test_skill\n---\n# Test\nBody.",
                    }
                ),
                expected_outcome="Persist a new skill document",
                rationale="Autonomous skill growth",
            )
        )

    assert result.success is False
    assert result.error == "approval_required"


@pytest.mark.asyncio
async def test_genesis_synthesizer_uses_amac_admission(tmp_path: Path, monkeypatch):
    import time

    from silex.autonomy.skill_synthesizer import (
        GenesisSynthesizer,
        PreferenceValidationResult,
        SkillSynthesisResult,
    )
    from silex.storage.database import Database

    class MockGenesisLLM:
        async def complete_json(self, *, schema, system_prompt, user_input, **kwargs):
            if schema == SkillSynthesisResult:
                return SkillSynthesisResult(
                    skill_name="deploy_helper",
                    description="Deploy artifacts to staging",
                    skill_md=(
                        "---\nname: deploy_helper\ndescription: Deploy\n---\n"
                        "# Deploy Helper\nRun the staging deploy script."
                    ),
                    python_script="print('deploy')",
                    dependencies=["requests"],
                )
            if schema == PreferenceValidationResult:
                return PreferenceValidationResult(is_safe=True, contradiction_reason="")
            raise ValueError(f"Unexpected schema: {schema}")

    db_path = tmp_path / "genesis.db"
    db = Database(str(db_path))
    await db.connect()

    skills_dir = tmp_path / "skills"
    monkeypatch.setattr("silex.autonomy.skill_synthesizer.KINTHIC_SKILLS", skills_dir)
    monkeypatch.setattr("silex.evolution.admission_control.KINTHIC_SKILLS", skills_dir)

    try:
        await db.execute(
            """
            INSERT INTO trajectories (trajectory_id, task_description, is_success, cumulative_latency, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("traj_genesis_1", "Deploy to staging", 1, 2.0, 100, time.time()),
        )
        for order, action in enumerate(("write_file", "run_deploy"), start=1):
            await db.execute(
                """
                INSERT INTO trajectory_steps (trajectory_id, step_order, action_name, tool_input, execution_output, epistemic_category, latency_ms, token_usage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("traj_genesis_1", order, action, "input", "ok", "fact", 50.0, 10),
            )

        synthesizer = GenesisSynthesizer(db, MockGenesisLLM(), kg=None)
        skill_name = await synthesizer.run()

        assert skill_name == "deploy_helper"
        skill_md = skills_dir / "deploy_helper" / "SKILL.md"
        assert skill_md.exists()
        content = skill_md.read_text(encoding="utf-8")
        assert "source: genesis" in content
        assert "Deploy Helper" in content
        assert (skills_dir / "deploy_helper" / "deploy_helper.py").exists()
        assert (
            skills_dir / "deploy_helper" / "requirements.txt"
        ).read_text() == "requests"
    finally:
        await db.close()


def test_catalog_sync_marks_seeded_skills_installed(tmp_path, monkeypatch):
    kinthic_skills = tmp_path / "home" / "skills"
    kinthic_skills.mkdir(parents=True)
    (kinthic_skills / "tell_joke.md").write_text("# joke", encoding="utf-8")

    registry_dir = tmp_path / "home" / "registry"
    registry_dir.mkdir(parents=True)
    catalog_path = registry_dir / "catalog.yaml"
    catalog_path.write_text(
        'version: "1.0"\nentries:\n  - name: tell_joke\n    type: skill\n    trust_level: core\n    installed: false\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("silex.utils.config.KINTHIC_SKILLS", kinthic_skills)
    monkeypatch.setattr("silex.utils.config.KINTHIC_HOME", tmp_path / "home")

    reg = KinthicRegistry()
    reg.registry_dir = registry_dir
    reg.catalog_path = catalog_path
    reg._catalog = None
    entries = reg.load_catalog()
    joke = next(e for e in entries if e["name"] == "tell_joke")
    assert joke["installed"] is True


def test_uninstall_core_skill_blocked(tmp_path, monkeypatch):
    kinthic_skills = tmp_path / "home" / "skills"
    kinthic_skills.mkdir(parents=True)
    skill_file = kinthic_skills / "tell_joke.md"
    skill_file.write_text("# joke", encoding="utf-8")

    registry_dir = tmp_path / "home" / "registry"
    registry_dir.mkdir(parents=True)
    catalog_path = registry_dir / "catalog.yaml"
    catalog_path.write_text(
        'version: "1.0"\nentries:\n  - name: tell_joke\n    type: skill\n    trust_level: core\n    installed: true\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("silex.utils.config.KINTHIC_SKILLS", kinthic_skills)
    monkeypatch.setattr("silex.utils.config.KINTHIC_HOME", tmp_path / "home")

    reg = KinthicRegistry()
    reg.registry_dir = registry_dir
    reg.catalog_path = catalog_path
    reg._catalog = None

    ok, msg = reg.uninstall("tell_joke")
    assert ok is False
    assert "core bundled" in msg
    assert skill_file.exists()


def test_safe_extract_zip_rejects_traversal(tmp_path):
    import io
    import zipfile

    from silex.plugins.registry import KinthicRegistry

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "bad")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        with pytest.raises(ValueError, match="Unsafe zip entry"):
            KinthicRegistry._safe_extract_zip(zf, tmp_path)
