"""
Unit tests for the A-MAC Admission Controller (Phase 7.4).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from silex.storage.database import Database
from silex.evolution.admission_control import (
    SkillAdmissionController,
    calculate_rouge_l,
)


def test_rouge_l_similarity():
    # Exact match
    assert calculate_rouge_l("hello world", "hello world") == pytest.approx(1.0)
    # Complete mismatch
    assert calculate_rouge_l("hello world", "foo bar") == pytest.approx(0.0)
    # Empty
    assert calculate_rouge_l("", "hello") == pytest.approx(0.0)
    # Partial match
    # LCS is "quick brown fox jumps" (len=5)
    # precision = 5/6, recall = 5/9, f1 = 2*(30/54)/(14/9) = 10/15 = 0.666
    sim = calculate_rouge_l(
        "the quick brown fox jumps over the lazy dog", "quick brown fox jumps over cats"
    )
    assert sim > 0.5
    assert sim < 1.0


@pytest.mark.asyncio
async def test_novelty_computation(tmp_path: Path):
    db_path = tmp_path / "test_eval.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        controller = SkillAdmissionController(db, skills_dir=skills_dir)

        # 1. No skills in directory -> Novelty should be 1.0
        assert await controller.compute_novelty_score(
            "deploy to production"
        ) == pytest.approx(1.0)

        # Write a skill file
        skill_file = skills_dir / "deploy.md"
        skill_file.write_text("deploy app to production container", encoding="utf-8")

        # 2. Exact match -> Novelty should be 0.0
        assert await controller.compute_novelty_score(
            "deploy app to production container"
        ) == pytest.approx(0.0)

        # 3. High overlap -> Low novelty
        nov = await controller.compute_novelty_score("deploy app to production node")
        assert nov < 0.3

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_admit_skill_gating(tmp_path: Path):
    db_path = tmp_path / "test_eval.db"
    db = Database(str(db_path))
    await db.connect()

    try:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        controller = SkillAdmissionController(db, skills_dir=skills_dir)

        # 1. Low quality skill (low utility/confidence, duplicate content)
        # S(m) = 0.15*0.1 + 0.20*0.2 + 0.20*1.0 + 0.05*1.0 + 0.40*0.1 = 0.015 + 0.04 + 0.20 + 0.05 + 0.04 = 0.345 < 0.70
        success, score = await controller.admit_skill(
            skill_name="bad_skill",
            category="tests",
            description="substandard skill",
            content="very duplicate text",
            utility_score=0.1,
            confidence_score=0.2,
            type_prior=0.1,
            threshold=0.70,
        )
        assert success is False
        assert score < 0.70
        # Files should not exist
        assert not (skills_dir / "bad_skill.md").exists()

        # 2. High quality skill
        # S(m) = 0.15*1.0 + 0.20*1.0 + 0.20*1.0 + 0.05*1.0 + 0.40*0.8 = 0.15 + 0.20 + 0.20 + 0.05 + 0.32 = 0.92 >= 0.70
        success, score = await controller.admit_skill(
            skill_name="good_skill",
            category="deployment",
            description="useful deployment skill",
            content="instructions to deploy artifacts securely",
            utility_score=1.0,
            confidence_score=1.0,
            type_prior=0.8,
            threshold=0.70,
        )
        assert success is True
        assert score >= 0.70

        # Files must be written correctly (nested layout under skills_dir/<name>/SKILL.md)
        nested_file = skills_dir / "good_skill" / "SKILL.md"
        assert nested_file.exists()
        assert not (skills_dir / "good_skill.md").exists()

        nested_content = nested_file.read_text(encoding="utf-8")
        assert "name: good_skill" in nested_content
        assert "source: evolution" in nested_content
        assert "amac_score:" in nested_content
        assert "instructions to deploy artifacts securely" in nested_content

        # Database row must exist
        row = await db.fetch_one(
            "SELECT * FROM admitted_memories WHERE skill_name = ?", ("good_skill",)
        )
        assert row is not None
        assert row["category"] == "deployment"
        assert row["composite_score"] == pytest.approx(score)

    finally:
        await db.close()
