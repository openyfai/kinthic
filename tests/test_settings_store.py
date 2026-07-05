from pathlib import Path

from silex.runtime.settings import RuntimeSettingsStore


def test_runtime_settings_store_persists_setup_and_pairing(tmp_path: Path):
    store = RuntimeSettingsStore(
        settings_path=tmp_path / "settings.json",
        secrets_path=tmp_path / "secrets.json",
    )

    store.save_settings(
        {
            "setup_completed": True,
            "provider": "openai",
            "model": "gpt-4.1-mini",
        }
    )
    store.set_provider_secret("openai", "test-key")
    code = store.create_pair_code(ttl_minutes=5)

    assert store.setup_status()["setup_completed"] is True
    assert store.setup_status()["provider"] == "openai"
    assert store.setup_status()["provider_configured"] is True

    assert store.consume_pair_code(code, 12345, "demo_user") is True
    assert store.is_telegram_user_allowed(12345) is True
    assert len(store.list_telegram_users()) == 1
