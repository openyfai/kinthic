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

    def __init__(self):
        self.skills_dir = VYN_SKILLS
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
            if file_path.stem.lower() in _SKIP_SKILL_NAMES:
                continue
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
