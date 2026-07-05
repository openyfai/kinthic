"""Tests for kinthic data backup / restore."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest


def _patch_kinthic_paths(monkeypatch, home: Path) -> None:
    paths = {
        "KINTHIC_HOME": home,
        "SILEX_DB": home / "storage" / "silex.db",
        "SILEX_VECTOR_DB": home / "storage" / "vector_db",
        "KINTHIC_BACKUPS": home / "workspace" / "backups",
        "KINTHIC_DAEMON_LOCK": home / "runtime" / "daemon.lock",
        "KINTHIC_SECRETS": home / "config" / "secrets.json",
    }
    import silex.utils.config as cfg
    import silex.ops.backup as backup

    for mod in (cfg, backup):
        for key, value in paths.items():
            if hasattr(mod, key) or mod is cfg:
                monkeypatch.setattr(mod, key, value)


def _seed_home(home: Path) -> Path:
    (home / "storage").mkdir(parents=True, exist_ok=True)
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "runtime").mkdir(parents=True, exist_ok=True)
    (home / "workspace" / "backups").mkdir(parents=True, exist_ok=True)

    marker = home / "config" / "restore-marker.txt"
    marker.write_text("brain-v1", encoding="utf-8")

    db_path = home / "storage" / "silex.db"
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS restore_test (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO restore_test (note) VALUES ('seed')")
        conn.commit()
    finally:
        conn.close()
    return marker


@pytest.fixture
def kinthic_home(tmp_path, monkeypatch):
    home = tmp_path / "kinthic"
    home.mkdir()
    _patch_kinthic_paths(monkeypatch, home)
    return home


def test_inspect_backup_requires_memory_db(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("config/rules.json", "{}")

    from silex.ops.backup import inspect_backup

    summary = inspect_backup(bad_zip)
    assert summary["valid"] is False
    assert any("storage/silex.db" in err for err in summary["errors"])


def test_roundtrip_backup_and_restore(kinthic_home):
    from silex.ops.backup import export_backup, restore_backup

    marker = _seed_home(kinthic_home)
    archive = kinthic_home / "backup.zip"

    export_backup(str(archive))
    assert archive.exists()

    marker.unlink()
    assert not marker.exists()

    summary = restore_backup(archive, apply=True, pre_backup=False)
    assert summary["valid"] is True
    assert summary["applied"] is True
    assert marker.read_text(encoding="utf-8") == "brain-v1"
    assert (kinthic_home / "storage" / "silex.db").exists()


def test_dry_run_does_not_mutate(kinthic_home):
    from silex.ops.backup import export_backup, restore_backup

    marker = _seed_home(kinthic_home)
    archive = kinthic_home / "backup.zip"
    export_backup(str(archive))
    marker.unlink()

    summary = restore_backup(archive, apply=False, pre_backup=False)
    assert summary["valid"] is True
    assert summary["applied"] is False
    assert not marker.exists()


def test_restore_preserves_local_secrets(kinthic_home):
    from silex.ops.backup import export_backup, restore_backup

    _seed_home(kinthic_home)
    secrets = kinthic_home / "config" / "secrets.json"
    secrets.write_text('{"local": "keep-me"}', encoding="utf-8")

    archive = kinthic_home / "backup.zip"
    export_backup(str(archive))

    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr("config/secrets.json", '{"local": "from-backup"}')

    summary = restore_backup(archive, apply=True, pre_backup=False)
    assert summary["valid"] is True
    assert json.loads(secrets.read_text(encoding="utf-8"))["local"] == "keep-me"


def test_restore_refuses_live_daemon(kinthic_home, monkeypatch):
    from silex.ops.backup import export_backup, restore_backup

    _seed_home(kinthic_home)
    archive = kinthic_home / "backup.zip"
    export_backup(str(archive))

    lock = kinthic_home / "runtime" / "daemon.lock"
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

    summary = restore_backup(archive, apply=True, pre_backup=False)
    assert summary["valid"] is False
    assert any("daemon is running" in err for err in summary["errors"])
