from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import uvicorn

from aria.llm.catalog import get_provider_defaults, list_providers
from aria.runtime.settings import RuntimeSettingsStore
from aria.utils.config import (
    allow_multi_writer,
    browser_actions_enabled,
    code_apply_enabled,
    get_web_host,
    get_web_port,
    telegram_public_mode_enabled,
    terminal_execution_enabled,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aria", description="ARIA local operator CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Run interactive local setup")
    subparsers.add_parser("doctor", help="Show local setup and security status")
    subparsers.add_parser("models", help="List supported providers and models")
    subparsers.add_parser("web", help="Run the ARIA web server")

    telegram_parser = subparsers.add_parser("telegram", help="Telegram utilities")
    telegram_sub = telegram_parser.add_subparsers(dest="telegram_command")
    telegram_sub.add_parser("run", help="Run the Telegram bot")
    telegram_sub.add_parser("pair", help="Generate a Telegram pairing code")

    return parser


def run_setup() -> None:
    store = RuntimeSettingsStore()
    current = store.load_settings()
    providers = list_providers()
    print("\nARIA setup\n")
    for index, provider in enumerate(providers, start=1):
        print(f"{index}. {provider['label']} ({provider['id']})")
    raw_choice = input(f"\nChoose provider [1-{len(providers)}] (default 1): ").strip() or "1"
    provider = providers[max(0, min(len(providers) - 1, int(raw_choice) - 1))]
    defaults = get_provider_defaults(provider["id"])
    models = provider["models"]
    for index, model in enumerate(models, start=1):
        tier = f" [{model.get('tier')}]" if model.get("tier") else ""
        print(f"  {index}. {model['label']}{tier}")
    model_choice = input(f"Choose model [1-{len(models)}] (default 1): ").strip() or "1"
    model = models[max(0, min(len(models) - 1, int(model_choice) - 1))]
    api_key = input("Paste provider API key (leave blank to skip): ").strip()
    web_api_key = input("Optional web API key for remote access (leave blank for localhost-only): ").strip()

    store.save_settings(
        {
            "setup_completed": True,
            "provider": provider["id"],
            "model": model["id"],
            "fast_model": defaults["fast_model"],
            "reasoning_model": defaults["reasoning_model"],
        }
    )
    if api_key:
        store.set_provider_secret(provider["id"], api_key)
    if web_api_key:
        store.set_web_api_key(web_api_key)

    print("\nSetup saved.")
    print(f"- Provider: {provider['label']}")
    print(f"- Model: {model['label']}")
    print("- Local settings stored in data/settings.json and data/secrets.json")


def run_doctor() -> None:
    store = RuntimeSettingsStore()
    settings = store.load_settings()
    status = store.setup_status()
    print("\nARIA doctor\n")
    print(f"Setup complete: {status['setup_completed']}")
    print(f"Provider: {status['provider']}")
    print(f"Model: {status['model']}")
    print(f"Provider key configured: {status['provider_configured']}")
    print(f"Web API key configured: {status['web_api_key_configured']}")
    print(f"Paired Telegram users: {status['paired_telegram_users']}")
    print(f"Approvals required: {settings.get('security', {}).get('require_tool_approvals', True)}")
    print(f"Browser actions enabled: {browser_actions_enabled()}")
    print(f"Terminal execution enabled: {terminal_execution_enabled()}")
    print(f"Direct code apply enabled: {code_apply_enabled()}")

    warnings: list[str] = []
    if telegram_public_mode_enabled():
        warnings.append("TELEGRAM_PUBLIC_MODE=true allows any Telegram user to reach this agent.")
    if terminal_execution_enabled():
        warnings.append("Terminal execution is enabled. Keep approvals on and prefer localhost-only access.")
    if code_apply_enabled():
        warnings.append("Direct code apply is enabled. Review autonomy settings before launch.")
    if allow_multi_writer():
        warnings.append("ARIA_ALLOW_MULTI_WRITER=true can corrupt shared local state if multiple processes write at once.")
    if get_web_host() not in {"127.0.0.1", "localhost", "::1"} and not status["web_api_key_configured"]:
        warnings.append("Remote web bind without an API key will fail. Set ARIA_WEB_API_KEY before exposing ARIA.")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("\nWarnings: none")


def run_models() -> None:
    print("\nARIA supported providers\n")
    for provider in list_providers():
        print(f"{provider['label']} ({provider['id']})")
        for model in provider["models"]:
            tier = f" [{model.get('tier')}]" if model.get("tier") else ""
            print(f"  - {model['label']} :: {model['id']}{tier}")
        print()


def run_web() -> None:
    from scripts import web_server

    uvicorn.run(web_server.app, host=get_web_host(), port=get_web_port())


def run_telegram() -> None:
    from scripts.telegram_bot import main as telegram_main

    telegram_main()


def generate_pair_code() -> None:
    store = RuntimeSettingsStore()
    code = store.create_pair_code()
    print(f"\nTelegram pairing code: {code}")
    print("Send it to your bot with /start CODE or /pair CODE")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        from scripts.run import main as run_main

        run_main()
        return

    if args.command == "setup":
        run_setup()
        return
    if args.command == "doctor":
        run_doctor()
        return
    if args.command == "models":
        run_models()
        return
    if args.command == "web":
        run_web()
        return
    if args.command == "telegram":
        if args.telegram_command == "pair":
            generate_pair_code()
            return
        run_telegram()
        return


if __name__ == "__main__":
    main()
