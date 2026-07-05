from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import cli


def test_cli_module_importable():
    assert callable(cli.main)


def test_models_command_prints_known_provider():
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        cli.run_models()
    output = buffer.getvalue()
    assert "Google Gemini" in output
    assert "gemini-2.5-flash" in output


def test_doctor_command_reports_status(tmp_path: Path):
    store = cli.RuntimeSettingsStore(
        settings_path=tmp_path / "settings.json",
        secrets_path=tmp_path / "secrets.json",
    )
    store.save_settings(
        {"setup_completed": True, "provider": "ollama", "model": "llama3.1"}
    )

    buffer = StringIO()
    with patch("scripts.cli.RuntimeSettingsStore", return_value=store):
        with patch("sys.stdout", buffer):
            cli.run_doctor()

    output = buffer.getvalue()
    assert "Setup complete: True" in output
    assert "Provider: ollama" in output
