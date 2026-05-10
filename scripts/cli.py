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
    doctor_parser = subparsers.add_parser("doctor", help="Show local setup and security status")
    doctor_parser.add_argument(
        "--ping",
        action="store_true",
        help="Run a tiny live API call to verify configured provider credentials",
    )
    subparsers.add_parser("models", help="List supported providers and models")
    subparsers.add_parser("web", help="Run the ARIA web server")

    telegram_parser = subparsers.add_parser("telegram", help="Telegram utilities")
    telegram_sub = telegram_parser.add_subparsers(dest="telegram_command")
    telegram_sub.add_parser("run", help="Run the Telegram bot")
    telegram_sub.add_parser("pair", help="Generate a Telegram pairing code")

    subparsers.add_parser("start", help="Start ARIA daemon in the background")
    subparsers.add_parser("stop", help="Stop the ARIA background daemon")

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


def run_doctor(*, ping: bool = False) -> None:
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
    print(
        "\nCatalog note: Model IDs are preset names from ARIA's catalog; the provider API "
        "validates them only when you chat or run `doctor --ping`. If you see an unknown-model error, "
        "pick another ID from `aria models` or Settings."
    )

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

    if ping:
        import asyncio

        from aria.llm.provider_test import ping_provider
        from aria.utils.config import get_provider_secret

        provider = str(settings.get("provider", "") or status.get("provider") or "gemini").strip()
        model_raw = str(settings.get("model", "") or "").strip()
        model = model_raw or None
        key = (get_provider_secret(provider, settings_store=store) or "").strip()
        if provider != "ollama" and not key:
            print(
                "\nLive provider check skipped: no API key stored for the selected provider.\n"
                "- Run `aria setup`, or finish the web setup wizard and click “Test provider”.\n"
                "- If the key is only in an env var, copy it into the runtime store via setup."
            )
        else:
            print("\nLive provider check (one small API call)…")
            result = asyncio.run(ping_provider(provider, key, model))
            if result.get("ok"):
                print(f"  [ok] {result.get('message', 'Connected.')}")
            else:
                print(f"  [fail] {result.get('message', 'Connectivity check failed.')}")
                if result.get("hint"):
                    print(f"  Hint: {result['hint']}")
                if result.get("code"):
                    print(f"  Code: {result['code']}")
                print(
                    "  If the error mentions an unknown or invalid model name, compare your selection "
                    "with `aria models` (catalog presets may not match your provider account)."
                )


def run_models() -> None:
    print("\nARIA supported providers\n")
    for provider in list_providers():
        print(f"{provider['label']} ({provider['id']})")
        for model in provider["models"]:
            tier = f" [{model.get('tier')}]" if model.get("tier") else ""
            print(f"  - {model['label']} :: {model['id']}{tier}")
        print()


def run_web() -> None:
    import subprocess
    import shutil
    import webbrowser
    from pathlib import Path
    import json
    import os

    # 1. UI Build Check
    web_dist = Path("aria/web_dist/index.html")
    ui_out = Path("aria-ui/out/index.html")
    
    if not web_dist.exists() and not ui_out.exists():
        if Path("aria-ui/package.json").exists() and shutil.which("npm"):
            print("\n✨ First run detected: Building the ARIA dashboard UI...")
            print("This usually takes 1-2 minutes.\n")
            try:
                subprocess.run(["npm", "install"], cwd="aria-ui", check=True)
                subprocess.run(["npm", "run", "build"], cwd="aria-ui", check=True)
                print("\n✅ Dashboard built successfully!\n")
            except subprocess.CalledProcessError:
                print("\n❌ Failed to build the UI. Check the output above.")
                return
        else:
            print("\n❌ Corrupted installation: The web dashboard is missing from this package.")
            print("Please run `pip install --upgrade openyfai-aria`.\n")
            return

    # 2. Duplicate Process Check
    lock_path = Path("data/.aria_lock")
    if lock_path.exists():
        try:
            lock_data = json.loads(lock_path.read_text(encoding="utf-8").strip())
            pid = lock_data.get("pid")
            if pid:
                os.kill(pid, 0)
                print(f"\n⚡ ARIA is already running in the background (PID {pid}).")
                print("Opening dashboard...")
                webbrowser.open(f"http://{get_web_host()}:{get_web_port()}")
                return
        except OSError:
            pass
        except Exception:
            pass

    from scripts import web_server
    uvicorn.run(
        web_server.app,
        host=get_web_host(),
        port=get_web_port(),
        ws_max_size=int(os.environ.get("ARIA_WS_MAX_MESSAGE_CHARS", "2000000")),
    )


def run_telegram() -> None:
    from scripts.telegram_bot import main as telegram_main

    telegram_main()


def generate_pair_code() -> None:
    store = RuntimeSettingsStore()
    code = store.create_pair_code()
    print(f"\nTelegram pairing code: {code}")
    print("Send it to your bot with /start CODE or /pair CODE")


def run_start() -> None:
    print("Generating and starting ARIA background daemon...")
    import sys
    import subprocess
    
    if sys.platform == "win32":
        print("Windows daemonization not fully implemented natively yet. Please run `aria web` in a persistent terminal or use NSSM.")
        return

    log_file = Path("data/aria.log").absolute()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                [sys.executable, "-m", "scripts.cli", "web"],
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )
        pid = proc.pid
        print(f"ARIA daemon started (PID {pid}). Logs at {log_file}")
        pid_path = Path("data/aria.pid")
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pid_path, "w") as f:
            f.write(str(pid))
    except Exception as e:
        print(f"Failed to start ARIA daemon: {e}")

def run_stop() -> None:
    import signal

    pid_file = Path("data/aria.pid")
    if not pid_file.exists():
        print("ARIA daemon is not running (no PID file found).")
        return

    raw = pid_file.read_text().strip()
    try:
        pid = int(raw)
    except ValueError:
        print(f"Corrupted PID file (contents: {raw!r}). Removing it.")
        pid_file.unlink(missing_ok=True)
        return

    # Verify the process actually exists before killing
    try:
        os.kill(pid, 0)
    except OSError:
        print(f"No running process with PID {pid}. Cleaning up stale PID file.")
        pid_file.unlink(missing_ok=True)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped ARIA (PID {pid})")
    except OSError as e:
        print(f"Failed to stop ARIA (PID {pid}): {e}")

    pid_file.unlink(missing_ok=True)

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
        run_doctor(ping=getattr(args, "ping", False))
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
    if args.command == "start":
        run_start()
        return
    if args.command == "stop":
        run_stop()
        return


if __name__ == "__main__":
    main()
