from pathlib import Path

from aria.utils.dashboard_static import resolve_dashboard_dir


def test_resolve_prefers_packaged_web_dist(tmp_path: Path) -> None:
    packaged = tmp_path / "aria_pkg"
    wd = packaged / "web_dist"
    wd.mkdir(parents=True)
    (wd / "index.html").write_text("<html></html>", encoding="utf-8")
    # Decoy repo path with out/ — should not win
    repo = tmp_path / "repo"
    alt = repo / "aria-ui" / "out"
    alt.mkdir(parents=True)
    (alt / "index.html").write_text("<html>other</html>", encoding="utf-8")

    picked = resolve_dashboard_dir(packaged_aria_pkg=packaged, repo_root_from_scripts=repo)
    assert picked == wd


def test_resolve_falls_back_to_aria_ui_out(tmp_path: Path) -> None:
    packaged = tmp_path / "aria_pkg"
    (packaged / "web_dist").mkdir(parents=True)

    repo = tmp_path / "repo"
    out = repo / "aria-ui" / "out"
    out.mkdir(parents=True)
    (out / "index.html").write_text("<html></html>", encoding="utf-8")

    picked = resolve_dashboard_dir(packaged_aria_pkg=packaged, repo_root_from_scripts=repo)
    assert picked == out


def test_resolve_returns_none_when_missing(tmp_path: Path) -> None:
    packaged = tmp_path / "aria_pkg"
    (packaged / "web_dist").mkdir(parents=True)
    repo = tmp_path / "repo"
    assert resolve_dashboard_dir(packaged_aria_pkg=packaged, repo_root_from_scripts=repo) is None
