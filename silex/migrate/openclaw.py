import json
import shutil
import re
from pathlib import Path
from typing import Any

from silex.utils.config import KINTHIC_HOME
from silex.utils.logger import setup_logger

log = setup_logger("kinthic.migrate.openclaw")

def _parse_json5(text: str) -> dict[str, Any]:
    """A very basic JSON5 parser that strips comments before standard JSON parsing."""
    # Strip single line comments
    text = re.sub(r'//.*', '', text)
    # Strip block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Strip trailing commas (very basic regex, might be brittle for complex strings)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    try:
        return json.loads(text)
    except Exception as e:
        log.warning(f"Failed to parse JSON5: {e}")
        return {}

def scan_openclaw(source_path: str | None = None) -> dict[str, Any]:
    """Scan an OpenClaw directory and report what can be migrated."""
    base_dir = Path(source_path).expanduser() if source_path else Path.home() / ".openclaw"
    
    report = {
        "found": False,
        "base_dir": str(base_dir),
        "skills_count": 0,
        "config_found": False,
        "identity_found": False,
    }
    
    if not base_dir.exists() or not base_dir.is_dir():
        return report
        
    report["found"] = True
    
    if (base_dir / "openclaw.json").exists():
        report["config_found"] = True
        
    workspace_dir = base_dir / "workspace"
    if workspace_dir.exists() and workspace_dir.is_dir():
        # count .md files except standard ones
        skills = [f for f in workspace_dir.glob("*.md") if f.name not in ["AGENTS.md", "SOUL.md", "MEMORY.md"]]
        report["skills_count"] = len(skills)
        if (workspace_dir / "SOUL.md").exists():
            report["identity_found"] = True
            
    return report

def import_openclaw(source_path: str | None = None, dry_run: bool = True) -> list[str]:
    """Import data from OpenClaw to Kinthic."""
    base_dir = Path(source_path).expanduser() if source_path else Path.home() / ".openclaw"
    kinthic_dir = Path(KINTHIC_HOME)
    
    logs = []
    
    if not base_dir.exists() or not base_dir.is_dir():
        logs.append(f"❌ OpenClaw directory not found at {base_dir}")
        return logs
        
    logs.append(f"📦 Starting migration from {base_dir} to {kinthic_dir}")
    if dry_run:
        logs.append("⚠️ DRY RUN MODE: No files will be modified.")
    else:
        kinthic_dir.mkdir(parents=True, exist_ok=True)
        
    config_file = base_dir / "openclaw.json"
    if config_file.exists():
        logs.append("📄 Found openclaw.json, please manually review the allowlists for Kinthic.")
        
    # Migrate Skills from Workspace
    workspace_dir = base_dir / "workspace"
    kinthic_skills = kinthic_dir / "skills"
    if workspace_dir.exists() and workspace_dir.is_dir():
        count = 0
        if not dry_run:
            kinthic_skills.mkdir(parents=True, exist_ok=True)
            
        for skill_file in workspace_dir.glob("*.md"):
            if skill_file.name in ["AGENTS.md", "SOUL.md", "MEMORY.md"]:
                continue
            if not dry_run:
                shutil.copy2(skill_file, kinthic_skills / skill_file.name)
            count += 1
        logs.append(f"🧩 Migrated {count} custom markdown skills.")
        
        if (workspace_dir / "SOUL.md").exists():
            logs.append("👤 Found SOUL.md identity file, please manually review it for Kinthic personas.")

    logs.append("✅ Migration complete.")
    logs.append("🔒 IMPORTANT: You must run `kinthic telegram` and /pair your account to ensure security boundaries are established.")
    return logs
