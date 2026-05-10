"""Resolve the directory FastAPI StaticFiles should use for the pre-built dashboard."""

from __future__ import annotations

from pathlib import Path


def resolve_dashboard_dir(*, packaged_aria_pkg: Path, repo_root_from_scripts: Path) -> Path | None:
    """Pick dashboard static root: packaged web_dist/, else aria-ui/out/ in repo checkout."""
    wd = packaged_aria_pkg / "web_dist"
    if (wd / "index.html").is_file():
        return wd
    out = repo_root_from_scripts / "aria-ui" / "out"
    if (out / "index.html").is_file():
        return out
    return None
