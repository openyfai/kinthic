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

    proposals_parser = subparsers.add_parser("proposals", help="Manage self-improvement proposals")
    proposals_sub = proposals_parser.add_subparsers(dest="proposals_command")
    proposals_sub.add_parser("list", help="List all pending proposals")
    approve_p = proposals_sub.add_parser("approve", help="Approve a proposal by ID prefix")
    approve_p.add_argument("proposal_id", help="Proposal ID or prefix")
    reject_p = proposals_sub.add_parser("reject", help="Reject a proposal by ID prefix")
    reject_p.add_argument("proposal_id", help="Proposal ID or prefix")

    return parser


async def run_interactive_setup() -> None:
    """The minimalist 'Apple Slab' interactive setup wizard."""
    from aria.ui.onboarding import OnboardingUI
    from rich.table import Table
    from rich.text import Text

    ui = OnboardingUI()
    store = RuntimeSettingsStore()
    providers = list_providers()

    # 1. Provider Selection
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, p in enumerate(providers, 1):
        table.add_row(Text(f"{i}.", style="dim"), Text(p["label"], style="bold white"))
    
    ui.render_step("Intelligence Core", table, subtitle="Choose your primary LLM provider")
    choice = ui.prompt(f"Select Provider [1-{len(providers)}]", default="1")
    provider = providers[max(0, min(len(providers) - 1, int(choice) - 1))]

    custom_base_url = ""
    custom_label = ""
    
    if provider["id"] == "custom":
        ui.render_step(
            "Universal Provider", 
            Text("Configure your custom endpoint.", justify="center"),
            subtitle="Display Name (e.g. My Private Llama)"
        )
        custom_label = ui.prompt("Display Name", default="Custom Model")
        
        ui.render_step(
            "Universal Provider", 
            Text(f"Configuring '{custom_label}'", justify="center"),
            subtitle="Base URL (e.g. https://api.proxy.com/v1)"
        )
        custom_base_url = ""
        while not custom_base_url:
            custom_base_url = ui.prompt("Base URL").strip()
        
        ui.render_step(
            "Universal Provider", 
            Text(f"Configuring '{custom_label}'", justify="center"),
            subtitle="Exact Model ID (e.g. mixtral-8x7b-instruct)"
        )
        model_id = ""
        while not model_id:
            model_id = ui.prompt("Model ID").strip()
            
        model = {"id": model_id, "label": custom_label}
        defaults = {"fast_model": model_id, "reasoning_model": model_id}
    else:
        # 2. Model Selection
        models = provider["models"]
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, m in enumerate(models, 1):
            tier = f"({m.get('tier')})" if m.get("tier") else ""
            table.add_row(Text(f"{i}.", style="dim"), Text(f"{m['label']} {tier}", style="bold white"))
        
        ui.render_step(provider["label"], table, subtitle=f"Select the active model for {provider['label']}")
        m_choice = ui.prompt(f"Select Model [1-{len(models)}]", default="1")
        model = models[max(0, min(len(models) - 1, int(m_choice) - 1))]
        defaults = get_provider_defaults(provider["id"])

    # 3. API Key Verification
    api_key = ""
    if provider["id"] != "ollama":
        while True:
            ui.render_step(
                "Authentication", 
                Text(f"Identity verification for {provider['label']}.", justify="center"),
                subtitle="Paste your API key below"
            )
            api_key = ui.prompt("API Key", password=True)
            if not api_key:
                break
            
            ui.render_step("Authentication", Text("Verifying connectivity...", style="dim", justify="center"))
            from aria.llm.provider_test import ping_provider
            result = await ping_provider(
                provider["id"], 
                api_key, 
                model["id"], 
                base_url=custom_base_url if provider["id"] == "custom" else None
            )
            
            if result.get("ok"):
                store.set_provider_secret(provider["id"], api_key)
                break
            else:
                ui.render_step(
                    "Authentication", 
                    Text("Invalid API key or connectivity failure.", style="bold red", justify="center"),
                    subtitle=result.get("message", "Check your key and try again.")
                )
                ui.prompt("Press Enter to retry")
    else:
        # Ollama check
        ui.render_step("Local Core", Text("Verifying local Ollama endpoint...", style="dim", justify="center"))
        from aria.llm.provider_test import ping_provider
        result = await ping_provider("ollama", "", model["id"])
        if not result.get("ok"):
            ui.render_step(
                "Local Core", 
                Text("Ollama unreachable.", style="bold red", justify="center"),
                subtitle=result.get("hint", "Ensure Ollama is running.")
            )
            ui.prompt("Press Enter to continue anyway")

    # 4. Telegram Pairing (The Magic Handshake)
    ui.render_step(
        "Telegram Link", 
        Text("Would you like to link ARIA to your Telegram account?", justify="center"),
        subtitle="Recommended for remote access"
    )
    wants_telegram = ui.prompt("Link Telegram? (y/n)", default="n").lower() == "y"
    
    if wants_telegram:
        ui.render_step(
            "Telegram Link", 
            Text("Enter your Telegram Bot Token.", justify="center"),
            subtitle="Get this from @BotFather"
        )
        bot_token = ui.prompt("Bot Token", password=True)
        if bot_token:
            from aria.utils.telegram_pairing import TelegramPairingSession
            session = TelegramPairingSession(bot_token)
            try:
                await session.get_bot_info()
                deep_link = session.get_deep_link()
                
                ui.render_step(
                    "Telegram Link", 
                    Text(f"Open this link in Telegram and click 'Start':\n\n{deep_link}", justify="center", style="bold white"),
                    subtitle="Waiting for handshake..."
                )
                
                # Background wait for the user to click Start
                chat_id = await session.wait_for_handshake(timeout_s=120)
                
                # Save telegram settings
                store.set_provider_secret("telegram", bot_token)
                store.add_paired_telegram_user(chat_id)
                
                ui.render_step("Telegram Link", Text("✓ Identity Verified. Account Linked.", style="bold white", justify="center"))
                await asyncio.sleep(1.5)
            except Exception as e:
                ui.render_step("Telegram Link", Text(f"Pairing failed: {str(e)}", style="bold red", justify="center"))
                ui.prompt("Press Enter to skip")

    # 5. Finalize
    settings_payload = {
        "setup_completed": True,
        "provider": provider["id"],
        "model": model["id"],
        "fast_model": defaults["fast_model"],
        "reasoning_model": defaults["reasoning_model"],
    }
    
    if custom_base_url:
        settings_payload["base_url"] = custom_base_url
    if custom_label:
        settings_payload["custom_label"] = custom_label

    store.save_settings(settings_payload)
    
    ui.render_step(
        "Activation Complete", 
        Text("ARIA cognitive core is now active.", justify="center"),
        subtitle="You can now run 'aria web' or 'aria telegram run'"
    )
    
    # Windows PATH check (Legacy)
    if os.name == "nt":
        import shutil
        import sys
        if not shutil.which("aria"):
            scripts_path = Path(sys.executable).parent / "Scripts"
            from rich.panel import Panel
            ui.console.print(Panel(
                Text(f"⚠️  'aria' is not on your PATH.\nFallback: {sys.executable} -m scripts.cli web", justify="center"),
                border_style="yellow"
            ))
            
    ui.prompt("Press Enter to exit")
    ui.clear()


def run_setup() -> None:
    asyncio.run(run_interactive_setup())


def run_doctor(*, ping: bool = False) -> None:
    store = RuntimeSettingsStore()
    settings = store.load_settings()
    status = store.setup_status()
    
    provider_label = status['provider']
    if status['provider'] == 'custom':
        provider_label = f"Custom ({settings.get('custom_label', 'Unknown')})"

    print("\nARIA doctor\n")
    print(f"Setup complete: {status['setup_completed']}")
    print(f"Provider: {provider_label}")
    print(f"Model: {status['model']}")
    print(f"Provider key configured: {status['provider_configured']}")
    print(f"Web API key configured: {status['web_api_key_configured']}")
    print(f"Paired Telegram users: {status['paired_telegram_users']}")
    print(f"Approvals required: {settings.get('security', {}).get('require_tool_approvals', True)}")
    print(f"Browser actions enabled: {browser_actions_enabled()}")
    print(f"Terminal execution enabled: {terminal_execution_enabled()}")
    print(f"Direct code apply enabled: {code_apply_enabled()}")
    
    warnings = []
    if os.name == "nt":
        warnings.append("Windows detected: data/secrets.json has no OS-level file permission protection. (Prefer Env Vars)")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    if ping:
        import asyncio
        from aria.llm.provider_test import ping_provider
        from aria.utils.config import get_provider_secret

        provider = str(settings.get("provider", "") or status.get("provider") or "gemini").strip()
        model = settings.get("model")
        key = (get_provider_secret(provider, settings_store=store) or "").strip()
        if provider != "ollama" and not key:
            print("\nLive provider check skipped: no API key stored.")
        else:
            print("\nLive provider check...")
            result = asyncio.run(ping_provider(provider, key, model))
            print(f"  [{'ok' if result.get('ok') else 'fail'}] {result.get('message')}")

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
    import json

    web_dist = Path("aria/web_dist/index.html")
    if not web_dist.exists():
        print("Web dashboard missing. Run 'pip install --upgrade openyfai-aria'.")
        return

    # Duplicate Process Check
    lock_path = Path("data/.aria_lock")
    if lock_path.exists():
        try:
            lock_data = json.loads(lock_path.read_text(encoding="utf-8").strip())
            pid = lock_data.get("pid")
            if pid:
                os.kill(pid, 0)
                print(f"\n⚡ ARIA is already running (PID {pid}). Opening dashboard...")
                webbrowser.open(f"http://{get_web_host()}:{get_web_port()}")
                return
        except OSError:
            pass

    from scripts import web_server
    uvicorn.run(web_server.app, host=get_web_host(), port=get_web_port())


def run_telegram() -> None:
    from scripts.telegram_bot import main as telegram_main
    telegram_main()


def generate_pair_code() -> None:
    store = RuntimeSettingsStore()
    code = store.create_pair_code()
    print(f"\nTelegram pairing code: {code}")


def run_start() -> None:
    import sys
    import subprocess
    if sys.platform == "win32":
        print("Use 'aria web' on Windows.")
        return
    subprocess.Popen([sys.executable, "-m", "scripts.cli", "web"], start_new_session=True)


def run_stop() -> None:
    import signal
    pid_file = Path("data/aria.pid")
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()


def run_proposals(command: str, proposal_id: str | None = None) -> None:
    from aria.storage.database import Database
    from aria.core.meta_reasoning import MetaReasoningEngine
    from aria.utils.config import DB_PATH

    async def _run():
        db = Database(str(DB_PATH))
        await db.connect()
        engine = MetaReasoningEngine(None, db) # type: ignore
        if command == "list":
            proposals = await engine.get_pending_proposals()
            for p in proposals: print(f"{p.id[:8]} {p.target_system} {p.description}")
        elif command in {"approve", "reject"}:
            await engine.update_status(proposal_id, command + "d") # type: ignore
    asyncio.run(_run())


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        from scripts.run import main as run_main
        run_main()
        return

    if args.command == "setup":
        run_setup()
    elif args.command == "doctor":
        run_doctor(ping=getattr(args, "ping", False))
    elif args.command == "models":
        run_models()
    elif args.command == "web":
        run_web()
    elif args.command == "telegram":
        if args.telegram_command == "pair":
            generate_pair_code()
        else:
            run_telegram()
    elif args.command == "start":
        run_start()
    elif args.command == "stop":
        run_stop()
    elif args.command == "proposals":
        run_proposals(getattr(args, "proposals_command", "list"), getattr(args, "proposal_id", None))


if __name__ == "__main__":
    main()
