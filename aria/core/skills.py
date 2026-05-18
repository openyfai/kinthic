from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from aria.memory.vector_store import VectorStore

from aria.utils.logger import setup_logger
from aria.utils.config import VYN_SKILLS

log = setup_logger("aria.skills")

# Filenames excluded from loading as executable skills (contributor docs, etc.).
_SKIP_SKILL_NAMES = frozenset({"readme"})


class SkillLoader:
    """
    Dynamically loads Markdown (.md) files from ~/.vyn/skills.
    This allows users to extend VYN's capabilities without writing Python code.
    """

    def __init__(self, vector_store: VectorStore | None = None):
        self.skills_dir = VYN_SKILLS
        self.skills: dict[str, str] = {}
        self.vector_store = vector_store
        self.collection = None

        if self.vector_store and self.vector_store.is_active:
            try:
                self.collection = self.vector_store.client.get_or_create_collection(
                    name="aria_skills",
                    embedding_function=self.vector_store.embedding_function
                )
            except Exception as e:
                log.warning(f"Could not initialize vector collection for skills: {e}")

    def load_all(self) -> int:
        """Scan the skills directory and load all markdown files."""
        self.skills.clear()
        
        if not self.skills_dir.exists():
            log.warning(f"Skills directory not found at {self.skills_dir}. Creating it.")
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return 0

        count = 0
        for file_path in self.skills_dir.glob("*.md"):
            if file_path.stem.lower() in _SKIP_SKILL_NAMES:
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    skill_name = file_path.stem
                    self.skills[skill_name] = content
                    count += 1

                    if self.collection:
                        self.collection.upsert(
                            documents=[content],
                            metadatas=[{"name": skill_name}],
                            ids=[f"skill_{skill_name}"]
                        )
            except Exception as e:
                log.error(f"Failed to load skill {file_path.name}: {e}")

        log.info(f"Loaded {count} Markdown skills from {self.skills_dir}")
        return count

    def get_relevant_skills(self, query: str, limit: int = 3) -> dict[str, str]:
        """Retrieve only the top matches relevant to the user query."""
        if not self.skills:
            return {}

        if not self.collection:
            # Fallback to returning all/first few skills if vector store is not active
            return dict(list(self.skills.items())[:limit])

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(limit, len(self.skills))
            )
            
            relevant = {}
            if results and results.get("metadatas") and results["metadatas"][0]:
                for meta in results["metadatas"][0]:
                    name = meta.get("name")
                    if name and name in self.skills:
                        relevant[name] = self.skills[name]
            return relevant
        except Exception as e:
            log.error(f"Error querying semantic skills: {e}")
            # Fallback
            return dict(list(self.skills.items())[:limit])

    def format_for_prompt(self, query: str | None = None) -> str:
        """Format matching/relevant loaded skills into a block for the system prompt."""
        skills_to_format = self.skills
        if query:
            skills_to_format = self.get_relevant_skills(query)

        if not skills_to_format:
            return ""

        sections = [
            "═══════════════════════════════════════════════════════════",
            "AVAILABLE SKILLS (Community Markdown Workflows)",
            "═══════════════════════════════════════════════════════════",
            "You have been trained with the following instruction packs.",
            "Follow these workflows exactly when the user's request matches the domain.",
            ""
        ]

        for name, content in skills_to_format.items():
            sections.append(f"<skill name=\"{name}\">")
            sections.append(content.strip())
            sections.append("</skill>\n")

        return "\n".join(sections)
