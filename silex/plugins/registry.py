"""
silex/plugins/registry.py — KronosHub local plugin & skill registry.

Maintains a catalog of available skills, tool plugins, and provider plugins
at ~/.kronos/registry/catalog.yaml.  The catalog can be:

  - Seeded automatically from the bundled skills and provider plugins.
  - Extended by installing community packages via :plugin install.
  - Refreshed from a remote URL (KRONOS_REGISTRY_URL env var).

Catalog entry schema:
  name:        str   — unique identifier
  type:        str   — skill | tool | provider
  version:     str   — semver
  description: str
  tags:        list[str]
  trust_level: str   — core | verified | community
  source:      str   — bundled | installed | remote
  url:         str   — download URL (for remote entries)
  sha256:      str   — hex digest for integrity check
  entry_file:  str   — filename or subpath within the package
  installed:   bool  — whether currently installed locally
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import urllib.request
from typing import Any

log = logging.getLogger("silex.plugins.registry")

DEFAULT_REGISTRY_URL = os.getenv(
    "KRONOS_REGISTRY_URL",
    "https://kronos.openyf.dev/registry/catalog.yaml",
)


class KronosRegistry:
    """Local plugin/skill registry backed by ~/.kronos/registry/catalog.yaml."""

    def __init__(self) -> None:
        from silex.utils.config import KRONOS_HOME
        self.registry_dir = KRONOS_HOME / "registry"
        self.catalog_path = self.registry_dir / "catalog.yaml"
        self._catalog: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Catalog I/O
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def load_catalog(self) -> list[dict[str, Any]]:
        """Load and return all catalog entries (seeding if first run)."""
        if self._catalog is not None:
            return self._catalog

        self._ensure_dir()
        if not self.catalog_path.exists():
            self.seed_builtin_catalog()
        else:
            self._catalog = self._read_catalog_file()

        return self._catalog or []

    def _read_catalog_file(self) -> list[dict[str, Any]]:
        try:
            import yaml
            with open(self.catalog_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("entries", [])
        except Exception as exc:
            log.warning("Could not read catalog: %s", exc)
            return []

    def _write_catalog(self, entries: list[dict]) -> None:
        self._ensure_dir()
        try:
            import yaml
            payload = {
                "version": "1.0",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "entries": entries,
            }
            with open(self.catalog_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
            self._catalog = entries
        except Exception as exc:
            log.error("Failed to write catalog: %s", exc)

    # ------------------------------------------------------------------
    # Seed from bundled assets
    # ------------------------------------------------------------------

    def seed_builtin_catalog(self) -> None:
        """Build catalog from bundled skills + provider plugins."""
        from silex.utils.config import PROJECT_ROOT

        bundled_catalog = PROJECT_ROOT / "registry" / "catalog.yaml"
        if bundled_catalog.exists():
            try:
                import yaml
                with open(bundled_catalog, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                entries = list(data.get("entries", []))
                if entries:
                    log.info("Seeded KronosHub catalog from bundled registry/catalog.yaml (%d entries)", len(entries))
                    self._write_catalog(entries)
                    return
            except Exception as exc:
                log.warning("Could not load bundled catalog.yaml: %s", exc)

        entries: list[dict] = []

        # 1. Bundled skills from repo skills/*.md
        skills_dir = PROJECT_ROOT / "skills"
        if skills_dir.exists():
            for md in sorted(skills_dir.glob("*.md")):
                if md.stem.lower() in {"readme"}:
                    continue
                desc = ""
                for line in md.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip().lstrip("#").strip()
                    if stripped:
                        desc = stripped[:120]
                        break
                entries.append({
                    "name": md.stem,
                    "type": "skill",
                    "version": "1.0.0",
                    "description": desc,
                    "tags": ["bundled"],
                    "trust_level": "core",
                    "source": "bundled",
                    "entry_file": md.name,
                    "installed": True,
                })

        # 2. Bundled provider plugins from E:/AGI/plugins/providers/
        providers_dir = PROJECT_ROOT / "plugins" / "providers"
        if providers_dir.exists():
            for provider_dir in sorted(providers_dir.iterdir()):
                if not provider_dir.is_dir():
                    continue
                yaml_path = provider_dir / "plugin.yaml"
                if not yaml_path.exists():
                    continue
                try:
                    import yaml
                    with open(yaml_path, encoding="utf-8") as f:
                        manifest = yaml.safe_load(f) or {}
                    entries.append({
                        "name": manifest.get("name", provider_dir.name),
                        "type": "provider",
                        "version": "1.0.0",
                        "description": manifest.get("description", ""),
                        "tags": ["provider", "llm"],
                        "trust_level": "core",
                        "source": "bundled",
                        "entry_file": "plugin.yaml",
                        "installed": True,
                    })
                except Exception:
                    pass

        log.info("Seeded KronosHub catalog with %d entries", len(entries))
        self._write_catalog(entries)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, type_filter: str | None = None) -> list[dict[str, Any]]:
        """Fuzzy-search catalog by name, description, and tags."""
        catalog = self.load_catalog()
        q = query.lower()
        results = []
        for entry in catalog:
            if type_filter and entry.get("type") != type_filter:
                continue
            score = 0
            name = entry.get("name", "").lower()
            desc = entry.get("description", "").lower()
            tags = " ".join(entry.get("tags", [])).lower()
            if q in name:
                score += 3
            if q in desc:
                score += 2
            if q in tags:
                score += 1
            if score:
                results.append((score, entry))
        results.sort(key=lambda x: -x[0])
        return [e for _, e in results]

    # ------------------------------------------------------------------
    # Install / Uninstall
    # ------------------------------------------------------------------

    def install(self, name_or_url: str) -> tuple[bool, str]:
        """
        Install a skill or tool plugin.

        Accepts:
          - A catalog entry name (looks up URL from catalog)
          - A direct https:// URL to a .md file (installs as skill)
          - A direct https:// URL to a .zip archive (installs as tool plugin)

        Returns (success: bool, message: str).
        """
        from silex.utils.config import KRONOS_SKILLS, KRONOS_PLUGINS_TOOLS

        catalog = self.load_catalog()

        # Try catalog lookup first
        entry = next(
            (e for e in catalog if e.get("name") == name_or_url), None
        )

        if entry is None and name_or_url.startswith("https://"):
            entry = {"name": name_or_url.split("/")[-1].split(".")[0],
                     "type": "skill" if name_or_url.endswith(".md") else "tool",
                     "url": name_or_url,
                     "sha256": "",
                     "trust_level": "community",
                     "source": "remote"}

        if entry is None:
            return False, f"'{name_or_url}' not found in catalog. Try: kronos skills search {name_or_url}"

        if entry.get("installed"):
            return False, f"'{entry['name']}' is already installed."

        if entry.get("source") == "bundled" or entry.get("trust_level") == "core":
            ok, msg = self.install_bundled(entry["name"])
            if ok:
                self._mark_installed(entry["name"])
            return ok, msg

        url = entry.get("url", "")
        if not url:
            return False, f"Catalog entry '{entry['name']}' has no download URL."

        try:
            log.info("Downloading %s from %s", entry["name"], url)
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                content_bytes = resp.read()

            # Integrity check
            if entry.get("sha256"):
                actual = hashlib.sha256(content_bytes).hexdigest()
                if actual != entry["sha256"]:
                    return False, (
                        f"SHA-256 mismatch for '{entry['name']}'. "
                        f"Expected {entry['sha256']}, got {actual}. Aborting."
                    )

            plugin_type = entry.get("type", "skill")

            if plugin_type == "skill":
                dest = KRONOS_SKILLS / f"{entry['name']}.md"
                dest.write_bytes(content_bytes)
                self._mark_installed(entry["name"])
                return True, f"Skill '{entry['name']}' installed to {dest}"

            elif plugin_type == "tool":
                # Expect a .zip archive containing plugin.yaml + tool.py
                import io
                import zipfile
                plugin_dest = KRONOS_PLUGINS_TOOLS / entry["name"]
                plugin_dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                    zf.extractall(plugin_dest)
                self._mark_installed(entry["name"])
                return True, f"Tool plugin '{entry['name']}' installed to {plugin_dest}"

            else:
                return False, f"Cannot auto-install type='{plugin_type}' — install manually."

        except Exception as exc:
            return False, f"Install failed: {exc}"

    def install_bundled(self, name: str) -> tuple[bool, str]:
        """Copy a bundled skill from the repo into ~/.kronos/skills/."""
        from silex.utils.config import PROJECT_ROOT, KRONOS_SKILLS

        KRONOS_SKILLS.mkdir(parents=True, exist_ok=True)
        src_md = PROJECT_ROOT / "skills" / f"{name}.md"
        if not src_md.exists():
            return False, f"Bundled skill '{name}' not found in package (missing {src_md.name})."

        dest_md = KRONOS_SKILLS / f"{name}.md"
        shutil.copy2(src_md, dest_md)

        for suffix in (".yaml", ".skill.yaml"):
            src_yaml = PROJECT_ROOT / "skills" / f"{name}{suffix}"
            if src_yaml.exists():
                shutil.copy2(src_yaml, KRONOS_SKILLS / src_yaml.name)
                break

        return True, f"Skill '{name}' installed to {dest_md}"

    def install_core_skills(self, names: list[str] | None = None) -> list[str]:
        """Install default onboarding skill set; returns list of installed names."""
        default = [
            "tell_joke",
            "repo_researcher",
            "write_release_notes",
            "telegram_setup",
            "daily_briefing",
        ]
        installed: list[str] = []
        for name in names or default:
            ok, _ = self.install(name)
            if ok:
                installed.append(name)
            else:
                ok2, _ = self.install_bundled(name)
                if ok2:
                    self._mark_installed(name)
                    installed.append(name)
        return installed

    def uninstall(self, name: str) -> tuple[bool, str]:
        """Remove an installed skill or tool plugin by name."""
        from silex.utils.config import KRONOS_SKILLS, KRONOS_PLUGINS_TOOLS, KRONOS_PLUGINS_SKILLS

        # Try flat skill
        skill_file = KRONOS_SKILLS / f"{name}.md"
        if skill_file.exists():
            skill_file.unlink()
            self._mark_uninstalled(name)
            return True, f"Skill '{name}' removed."

        # Try nested skill folder
        for skill_dir in [KRONOS_SKILLS / name, KRONOS_PLUGINS_SKILLS / name]:
            if skill_dir.is_dir():
                shutil.rmtree(skill_dir)
                self._mark_uninstalled(name)
                return True, f"Skill '{name}' removed."

        # Try tool plugin folder
        tool_dir = KRONOS_PLUGINS_TOOLS / name
        if tool_dir.is_dir():
            shutil.rmtree(tool_dir)
            self._mark_uninstalled(name)
            return True, f"Tool plugin '{name}' removed."

        # Check if it's a core (bundled) entry
        catalog = self.load_catalog()
        entry = next((e for e in catalog if e.get("name") == name), None)
        if entry and entry.get("trust_level") == "core":
            return False, f"'{name}' is a core bundled plugin and cannot be removed."

        return False, f"'{name}' not found in installed plugins or skills."

    def _mark_installed(self, name: str) -> None:
        entries = self.load_catalog()
        for e in entries:
            if e.get("name") == name:
                e["installed"] = True
        self._write_catalog(entries)

    def _mark_uninstalled(self, name: str) -> None:
        entries = self.load_catalog()
        for e in entries:
            if e.get("name") == name:
                e["installed"] = False
        self._write_catalog(entries)

    # ------------------------------------------------------------------
    # Remote refresh
    # ------------------------------------------------------------------

    def refresh_from_remote(self, url: str | None = None) -> tuple[bool, str]:
        """
        Fetch the remote registry catalog and merge it with local entries.
        Only adds new entries; does not overwrite existing local metadata.
        """
        url = url or DEFAULT_REGISTRY_URL
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
            import yaml
            remote_data = yaml.safe_load(raw) or {}
            remote_entries: list[dict] = remote_data.get("entries", [])
        except Exception as exc:
            return False, f"Could not fetch remote registry: {exc}"

        local = self.load_catalog()
        local_names = {e.get("name") for e in local}
        added = 0
        for entry in remote_entries:
            if entry.get("name") not in local_names:
                entry.setdefault("installed", False)
                entry.setdefault("source", "remote")
                local.append(entry)
                added += 1

        self._write_catalog(local)
        return True, f"Registry refreshed: {added} new entries added from {url}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_all(self, type_filter: str | None = None) -> list[dict[str, Any]]:
        """Return all catalog entries, optionally filtered by type."""
        entries = self.load_catalog()
        if type_filter:
            return [e for e in entries if e.get("type") == type_filter]
        return entries

    def format_list(self, entries: list[dict]) -> str:
        """Format a list of catalog entries as readable text."""
        if not entries:
            return "No results found."
        lines = []
        for e in entries:
            badge = {"core": "[core]", "verified": "[✓]", "community": "[community]"}.get(
                e.get("trust_level", "community"), ""
            )
            installed = " (installed)" if e.get("installed") else ""
            lines.append(
                f"  {badge} {e.get('name')} ({e.get('type', '?')}) "
                f"v{e.get('version', '?')}{installed}"
            )
            if e.get("description"):
                lines.append(f"       {e['description'][:80]}")
        return "\n".join(lines)


# Module-level singleton
_registry: KronosRegistry | None = None


def get_registry() -> KronosRegistry:
    global _registry
    if _registry is None:
        _registry = KronosRegistry()
    return _registry
