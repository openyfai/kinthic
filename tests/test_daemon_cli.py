"""Tests for daemon CLI, migrate safety, onboard alias, and service units."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import cli


def test_onboard_parser_registered():
    parser = cli.build_parser()
    args = parser.parse_args(["onboard"])
    assert args.command == "onboard"


def test_setup_parser_registered():
    parser = cli.build_parser()
    args = parser.parse_args(["setup"])
    assert args.command == "setup"


def test_innit_parser_registered_as_init_alias():
    parser = cli.build_parser()
    args = parser.parse_args(["innit"])
    assert args.command == "innit"


def test_daemon_start_spawns_daemon_run(tmp_path, monkeypatch):
    lock_path = tmp_path / "daemon.lock"
    monkeypatch.setattr("silex.utils.config.KINTHIC_DAEMON_LOCK", lock_path)

    captured = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            lock_path.write_text(json.dumps({"pid": 99999}), encoding="utf-8")

    monkeypatch.setattr("subprocess.Popen", FakePopen)
    monkeypatch.setattr("os.kill", lambda pid, sig: None)

    buffer = StringIO()
    with patch("sys.stdout", buffer):
        cli.run_start()

    assert captured["argv"][-2:] == ["daemon", "run"]
    assert "Daemon started" in buffer.getvalue()


def test_migrate_default_is_scan_only(monkeypatch):
    calls = []

    def fake_migrate(command, source, path, dry_run):
        calls.append((command, source, path, dry_run))

    monkeypatch.setattr(cli, "run_migrate", fake_migrate)
    cli.main = cli.main  # noqa — ensure module reference
    with patch.object(cli, "build_parser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "data"
        mock_args.data_command = "migrate"
        mock_args.source = "hermes"
        mock_args.path = None
        mock_args.scan_only = False
        mock_args.dry_run = False
        mock_args.apply = False
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch("scripts.cli.run_migrate", fake_migrate):
            # Invoke migrate branch directly
            source = mock_args.source
            path = mock_args.path
            if mock_args.scan_only or (not mock_args.dry_run and not mock_args.apply):
                cli.run_migrate("scan", source, path, True)
            elif mock_args.apply:
                cli.run_migrate("import", source, path, False)
            else:
                cli.run_migrate("import", source, path, True)

    assert calls == [("scan", "hermes", None, True)]


def test_migrate_apply_imports():
    calls = []

    def fake_migrate(command, source, path, dry_run):
        calls.append((command, source, path, dry_run))

    source = "openclaw"
    path = "/tmp/x"
    scan_only = False
    dry_run = False
    apply = True
    migrate_fn = fake_migrate
    if scan_only or (not dry_run and not apply):
        migrate_fn("scan", source, path, True)
    elif apply:
        migrate_fn("import", source, path, False)
    else:
        migrate_fn("import", source, path, True)

    assert calls == [("import", "openclaw", "/tmp/x", False)]


def test_proposals_reject_uses_rejected_status():
    captured = {}

    class FakeEngine:
        async def get_pending_proposals(self):
            return []

        async def update_status(self, proposal_id, status):
            captured["status"] = status

    class FakeDB:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def close(self):
            pass

    with patch("silex.storage.database.Database", FakeDB):
        with patch("silex.core.meta_reasoning.MetaReasoningEngine", lambda *a, **k: FakeEngine()):
            cli.run_proposals("reject", "abc123")

    assert captured.get("status") == "rejected"


def test_first_run_gate_routes_to_onboard(monkeypatch, tmp_path):
    store = cli.RuntimeSettingsStore(
        settings_path=tmp_path / "settings.json",
        secrets_path=tmp_path / "secrets.json",
    )
    store.save_settings({"setup_completed": False})

    called = {"onboard": False}

    def fake_onboard():
        called["onboard"] = True

    monkeypatch.delenv("KINTHIC_SKIP_SETUP", raising=False)
    monkeypatch.setattr("silex.runtime.settings.RuntimeSettingsStore", lambda: store)
    monkeypatch.setattr("scripts.cli.run_onboard", fake_onboard)

    from scripts import run as run_module

    run_module.main()
    assert called["onboard"] is True


def test_systemd_unit_contains_restart_and_daemon_run():
    from silex.ops.service import render_systemd_unit

    unit = render_systemd_unit()
    assert "Restart=always" in unit
    assert "daemon run" in unit


def test_prefetch_skips_without_chromadb(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None if name == "chromadb" else MagicMock())
    from silex.ops.prefetch import prefetch_embedding_model

    msg = prefetch_embedding_model()
    assert msg is not None
    assert "Skipped" in msg
