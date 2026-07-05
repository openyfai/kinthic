"""
Skill Distillation and A-MAC (Adaptive Memory Admission Control) Engine (Phase 7.4).

Evaluates candidate skills for quality, novelty (via ROUGE-L similarity), and admits
them to persistent memory and the skill registry.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from silex.storage.database import Database
from silex.utils.config import KINTHIC_SKILLS
from silex.utils.logger import setup_logger

log = setup_logger("silex.evolution.admission_control")

# ---------------------------------------------------------------------------
# ROUGE-L Helper
# ---------------------------------------------------------------------------

def calculate_rouge_l(text1: str, text2: str) -> float:
    """Calculates the ROUGE-L (Longest Common Subsequence) F1 similarity between two texts."""
    words1 = text1.lower().split()
    words2 = text2.lower().split()
    if not words1 or not words2:
        return 0.0
    
    m = len(words1)
    n = len(words2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if words1[i - 1] == words2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
                
    lcs_len = dp[m][n]
    precision = lcs_len / n
    recall = lcs_len / m
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


# ---------------------------------------------------------------------------
# SkillAdmissionController
# ---------------------------------------------------------------------------

class SkillAdmissionController:
    """
    Decides whether a newly synthesized capability or memory is admitted into
    Kinthic's persistent database and active skills directory using ROUGE-L and A-MAC.
    """

    def __init__(self, db: Database, skills_dir: Path | str | None = None):
        self.db = db
        if skills_dir is None:
            self.skills_dir = KINTHIC_SKILLS
        else:
            self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    async def compute_novelty_score(self, content: str) -> float:
        """
        Computes novelty: 1.0 minus the maximum ROUGE-L similarity against
        all currently active skills in the registry.
        """
        active_skills = list(self.skills_dir.glob("*.md")) + list(self.skills_dir.glob("**/SKILL.md"))
        if not active_skills:
            return 1.0

        max_similarity = 0.0
        for skill_path in active_skills:
            try:
                existing_content = skill_path.read_text(encoding="utf-8")
                # Strip YAML headers if present to compare actual instruction similarity
                if existing_content.startswith("---"):
                    parts = existing_content.split("---", 2)
                    if len(parts) >= 3:
                        existing_content = parts[2]
                
                similarity = calculate_rouge_l(content, existing_content)
                if similarity > max_similarity:
                    max_similarity = similarity
            except Exception as e:
                log.warning(f"Failed to read existing skill {skill_path} for similarity comparison: {e}")

        # Novelty is inverse of max overlap
        novelty = 1.0 - max_similarity
        log.debug(f"Novelty check complete. Max similarity overlap: {max_similarity:.4f}, Novelty: {novelty:.4f}")
        return novelty

    def compute_amac_score(
        self,
        utility: float,
        confidence: float,
        novelty: float,
        recency: float = 1.0,
        type_prior: float = 0.8
    ) -> float:
        """
        Calculates A-MAC composite memory quality score:
        S(m) = 0.15*U(m) + 0.20*C(m) + 0.20*N(m) + 0.05*R(m) + 0.40*T(m)
        """
        score = (
            0.15 * utility +
            0.20 * confidence +
            0.20 * novelty +
            0.05 * recency +
            0.40 * type_prior
        )
        return score

    async def admit_skill(
        self,
        skill_name: str,
        category: str,
        description: str,
        content: str,
        utility_score: float = 1.0,
        confidence_score: float = 1.0,
        type_prior: float = 0.8,
        origin_trajectory_id: str | None = None,
        session_id: str | None = None,
        user_id: str = "default_user",
        threshold: float = 0.70,
        source: str = "evolution",
        author: str | None = None,
    ) -> tuple[bool, float]:
        """
        Orchestrates skill admission:
          1. Calculate Novelty.
          2. Calculate A-MAC score.
          3. Verify if score meets threshold.
          4. If passes, save to DB `admitted_memories` and write to disk in agentskills.io format.
        """
        log.info(f"Evaluating candidate skill '{skill_name}' for admission...")
        
        # 1. Compute scores
        novelty_score = await self.compute_novelty_score(content)
        composite_score = self.compute_amac_score(
            utility=utility_score,
            confidence=confidence_score,
            novelty=novelty_score,
            recency=1.0,
            type_prior=type_prior
        )

        log.info(f"Skill '{skill_name}' evaluated with A-MAC score: {composite_score:.4f} (threshold={threshold:.2f})")
        if composite_score < threshold:
            log.warning(f"Skill '{skill_name}' rejected due to insufficient A-MAC quality score.")
            return False, composite_score

        # 2. Write in agentskills.io format to:
        #    active/<category>/<skill>/SKILL.md
        #    And a flat file: <skill>.md (for the flat loader)
        frontmatter = (
            "---\n"
            f"name: {skill_name}\n"
            f"description: {description}\n"
            f"category: {category}\n"
            f"source: {source}\n"
            f"author: {author or source}\n"
            f"amac_score: {composite_score:.4f}\n"
            "---\n\n"
        )
        full_markdown_payload = frontmatter + content

        nested_dir = self.skills_dir / skill_name
        nested_dir.mkdir(parents=True, exist_ok=True)
        nested_file = nested_dir / "SKILL.md"
        nested_file.write_text(full_markdown_payload, encoding="utf-8")

        log.info(f"Wrote skill file to {nested_file}")

        # 3. Log into database admitted_memories
        memory_id = f"mem_skill_{hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:12]}"
        integrity_hash = hashlib.sha256(full_markdown_payload.encode("utf-8")).hexdigest()

        await self.db.execute(
            """
            INSERT OR REPLACE INTO admitted_memories (
                memory_id, user_id, session_id, content, content_type,
                utility_score, confidence_score, novelty_score, recency_score,
                type_prior, composite_score, admitted_at, integrity_hash,
                origin_trajectory_id, skill_name, category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id, user_id, session_id, full_markdown_payload, "plan",
                utility_score, confidence_score, novelty_score, 1.0,
                type_prior, composite_score, time.time(), integrity_hash,
                origin_trajectory_id, skill_name, category
            )
        )

        log.info(f"Skill '{skill_name}' successfully admitted and logged to database.")
        return True, composite_score
