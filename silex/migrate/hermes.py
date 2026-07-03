import yaml
import shutil
from pathlib import Path
from typing import Any

from silex.utils.config import KINTHIC_HOME, KINTHIC_SECRETS
from silex.utils.logger import setup_logger

log = setup_logger("kinthic.migrate.hermes")

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"Failed to load yaml {path}: {e}")
        return {}

def scan_hermes(source_path: str | None = None) -> dict[str, Any]:
    """Scan a Hermes directory and report what can be migrated."""
    base_dir = Path(source_path).expanduser() if source_path else Path.home() / ".hermes"
    
    report = {
        "found": False,
        "base_dir": str(base_dir),
        "skills_count": 0,
        "env_found": False,
        "config_found": False,
        "persona_found": False,
    }
    
    if not base_dir.exists() or not base_dir.is_dir():
        return report
        
    report["found"] = True
    
    if (base_dir / ".env").exists():
        report["env_found"] = True
        
    if (base_dir / "config.yaml").exists():
        report["config_found"] = True
        
    skills_dir = base_dir / "skills"
    if skills_dir.exists() and skills_dir.is_dir():
        report["skills_count"] = len(list(skills_dir.glob("*.md")))
        
    # check for persona / memory
    if (base_dir / "memories" / "USER.md").exists():
        report["persona_found"] = True
        
    return report

def import_hermes(source_path: str | None = None, dry_run: bool = True) -> list[str]:
    """Import data from Hermes to Kinthic."""
    base_dir = Path(source_path).expanduser() if source_path else Path.home() / ".hermes"
    kinthic_dir = Path(KINTHIC_HOME)
    
    logs = []
    
    if not base_dir.exists() or not base_dir.is_dir():
        logs.append(f"❌ Hermes directory not found at {base_dir}")
        return logs
        
    logs.append(f"📦 Starting migration from {base_dir} to {kinthic_dir}")
    if dry_run:
        logs.append("⚠️ DRY RUN MODE: No files will be modified.")
    else:
        kinthic_dir.mkdir(parents=True, exist_ok=True)
        
    # Migrate .env secrets to secrets.json loosely
    env_file = base_dir / ".env"
    if env_file.exists():
        logs.append("📄 Found .env file, migrating secrets...")
        import json
        secrets = {}
        if not dry_run and KINTHIC_SECRETS.exists():
            try:
                secrets = json.loads(KINTHIC_SECRETS.read_text())
            except Exception:
                pass
                
        env_text = env_file.read_text(encoding="utf-8")
        migrated_keys = 0
        for line in env_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if not dry_run:
                    secrets[k] = v
                migrated_keys += 1
                
        if not dry_run:
            KINTHIC_SECRETS.write_text(json.dumps(secrets, indent=2))
        logs.append(f"  ✓ Migrated {migrated_keys} keys.")

    # Migrate Skills
    skills_dir = base_dir / "skills"
    kinthic_skills = kinthic_dir / "skills"
    if skills_dir.exists() and skills_dir.is_dir():
        count = 0
        if not dry_run:
            kinthic_skills.mkdir(parents=True, exist_ok=True)
            
        for skill_file in skills_dir.glob("*.md"):
            if not dry_run:
                shutil.copy2(skill_file, kinthic_skills / skill_file.name)
            count += 1
        logs.append(f"🧩 Migrated {count} skills.")

    # Migrate Persona / Config logic...
    user_md = base_dir / "memories" / "USER.md"
    if user_md.exists():
        logs.append("👤 Found USER.md identity file, please manually review it for Kinthic personas.")

    logs.append("✅ Migration complete.")
    logs.append("🔒 IMPORTANT: You must run `kinthic telegram` and /pair your account to ensure security boundaries are established.")
    return logs
