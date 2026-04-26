import os
from pathlib import Path
from aria.utils.logger import setup_logger

log = setup_logger("aria.skills")

class SkillLoader:
    """
    Dynamically loads Markdown (.md) files from the /skills directory.
    This allows the community to extend ARIA's capabilities without writing Python code.
    """

    def __init__(self, skills_dir: str = "skills"):
        # Resolve the absolute path from the project root
        self.skills_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / skills_dir
        self.skills: dict[str, str] = {}

    def load_all(self) -> int:
        """Scan the skills directory and load all markdown files."""
        self.skills.clear()
        
        if not self.skills_dir.exists():
            log.warning(f"Skills directory not found at {self.skills_dir}. Creating it.")
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return 0

        count = 0
        for file_path in self.skills_dir.glob("*.md"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    skill_name = file_path.stem
                    self.skills[skill_name] = content
                    count += 1
            except Exception as e:
                log.error(f"Failed to load skill {file_path.name}: {e}")

        log.info(f"Loaded {count} Markdown skills from {self.skills_dir}")
        return count

    def format_for_prompt(self) -> str:
        """Format all loaded skills into a block for the system prompt."""
        if not self.skills:
            return ""

        sections = [
            "═══════════════════════════════════════════════════════════",
            "AVAILABLE SKILLS (Community Markdown Workflows)",
            "═══════════════════════════════════════════════════════════",
            "You have been trained with the following instruction packs.",
            "Follow these workflows exactly when the user's request matches the domain.",
            ""
        ]

        for name, content in self.skills.items():
            sections.append(f"<skill name=\"{name}\">")
            sections.append(content.strip())
            sections.append("</skill>\n")

        return "\n".join(sections)
