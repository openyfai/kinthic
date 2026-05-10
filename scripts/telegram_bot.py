import os
import sys
import asyncio
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aria.core.cognitive_loop import CognitiveLoop
from aria.runtime.settings import RuntimeSettingsStore
from aria.utils.config import telegram_public_mode_enabled
from aria.utils.logger import setup_logger

log = setup_logger("aria.telegram")

# Global singleton for the Cognitive Loop
aria_loop = None
settings_store = RuntimeSettingsStore()


def _env_allowlist() -> list[int]:
    allowed_users_env = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    if not allowed_users_env:
        return []
    try:
        return [int(x.strip()) for x in allowed_users_env.split(",") if x.strip()]
    except ValueError:
        log.error("ALLOWED_TELEGRAM_USERS contains non-integer values!")
        return []


def _telegram_user_allowed(user_id: int) -> bool:
    public_mode = telegram_public_mode_enabled()
    if public_mode:
        return True
    if settings_store.is_telegram_user_allowed(user_id):
        return True
    return user_id in _env_allowlist()


async def _send_pending_approvals(update: Update) -> None:
    approvals = await aria_loop.tool_registry.get_pending_approvals()
    if not approvals:
        await update.message.reply_text("No pending tool approvals.")
        return
    lines = []
    for approval in approvals[:10]:
        lines.append(
            f"`{approval['id'][:8]}` · {approval['tool_name']} · {approval['risk_level']}\n"
            f"{approval['reason']}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def pair_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = " ".join(context.args).strip().upper()
    if not code:
        await update.message.reply_text("Usage: /pair <code>")
        return
    user = update.effective_user
    paired = settings_store.consume_pair_code(code, user.id, user.username)
    if paired:
        await update.message.reply_text("Pairing successful. You can now use this ARIA bot from Telegram.")
    else:
        await update.message.reply_text("That pairing code is invalid or expired.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    user_id = update.effective_user.id
    if context.args:
        code = context.args[0].strip().upper()
        if settings_store.consume_pair_code(code, user_id, update.effective_user.username):
            await update.message.reply_text("Pairing successful. ARIA is now linked to your Telegram account.")
            return
    await update.message.reply_text(
        "👋 Hello! I am ARIA — a local-first cognitive agent.\n\n"
        "My engine is online. I have access (within policy) to your tools, memory, "
        "and knowledge graph. How can I help you today?\n\n"
        f"Your Telegram ID: `{user_id}`\n"
        "If the operator generated a pairing code, send `/start CODE` or `/pair CODE`.",
        parse_mode="Markdown"
    )


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Telegram user: `{user.id}`\nUsername: `{user.username or 'unknown'}`",
        parse_mode="Markdown",
    )


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings_store.revoke_telegram_user(update.effective_user.id)
    await update.message.reply_text("This Telegram account has been unpaired from ARIA.")


async def approvals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied. Pair this account before requesting approvals.")
        return
    await _send_pending_approvals(update)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied. Pair this account before requesting status.")
        return
    health = await aria_loop.get_health_status()
    await update.message.reply_text(
        "ARIA status:\n"
        f"- Provider: {health.get('provider')}\n"
        f"- Model: {health.get('model')}\n"
        f"- Session: {health.get('current_session') or 'none'}\n"
        f"- Browser tool: {'on' if health.get('browser_registered') else 'off'}"
    )


async def approval_decision_command(update: Update, context: ContextTypes.DEFAULT_TYPE, decision: str) -> None:
    if not _telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied. Pair this account before resolving approvals.")
        return
    approval_id = " ".join(context.args).strip()
    if not approval_id:
        await update.message.reply_text(f"Usage: /{decision} <approval-id>")
        return
    matches = await aria_loop.tool_registry.get_pending_approvals()
    match = next((item for item in matches if item["id"].startswith(approval_id)), None)
    if not match:
        await update.message.reply_text("Approval not found.")
        return
    ok = await aria_loop.tool_registry.resolve_approval(match["id"], "approved" if decision == "approve" else "rejected")
    await update.message.reply_text("Approval updated." if ok else "Failed to update approval.")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await approval_decision_command(update, context, "approve")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await approval_decision_command(update, context, "reject")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pass incoming Telegram messages into ARIA's Cognitive Loop."""
    user_text = update.message.text or update.message.caption or ""
    
    # Process attachments
    images = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        images = [{"mime": "image/jpeg", "bytes": bytes(img_bytes)}]
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        file = await context.bot.get_file(update.message.document.file_id)
        img_bytes = await file.download_as_bytearray()
        images = [{"mime": update.message.document.mime_type, "bytes": bytes(img_bytes)}]

    if not user_text and not images:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not _telegram_user_allowed(user_id):
        # Auto-detect if they just pasted the pairing code directly
        potential_code = user_text.strip().upper()
        if potential_code.startswith("PAIR-"):
            if settings_store.consume_pair_code(potential_code, user_id, update.effective_user.username):
                await update.message.reply_text("Pairing successful. Connection secured.\n\nHi, I'm ARIA. What are we working on today?")
                return
            
        log.warning(f"Unauthorized access attempt from User ID: {user_id}")
        await update.message.reply_text(
            f"🚫 **Access Denied**\n\n"
            f"Send your exact pairing code (eg. `PAIR-XYZ`) to secure this connection.\n"
            f"Your Telegram ID: `{user_id}`",
            parse_mode="Markdown"
        )
        return
        
    # Show "typing..." indicator while ARIA thinks
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    try:
        # Route the message into the core agent loop!
        cognitive = await aria_loop.process(user_text, images=images)
        
        # -------------------------------------------------------------------------
        # STABILITY: Markdown Fallback
        # -------------------------------------------------------------------------
        try:
            # Attempt to send with Markdown formatting
            await update.message.reply_text(
                cognitive.response, 
                parse_mode='Markdown'
            )
        except Exception as parse_error:
            log.error(f"Markdown parse failed, falling back to plain text: {parse_error}")
            # If Telegram rejects the formatting, strip it and send as plain text
            await update.message.reply_text(
                f"*(Markdown formatting stripped for stability)*\n\n{cognitive.response}"
            )
        
    except Exception as e:
        log.error(f"Error processing message: {e}")
        try:
            # SECURITY: Do NOT send raw exception to user — it may contain
            # internal paths, API keys, or stack traces
            await update.message.reply_text(
                "⚠️ I encountered an internal error while processing your message. "
                "Please try again in a moment."
            )
        except Exception:
            pass

async def post_init(application: ApplicationBuilder) -> None:
    """Initialize ARIA's engine after the Telegram bot starts up."""
    global aria_loop
    log.info("Initializing ARIA Cognitive Engine...")
    aria_loop = CognitiveLoop()
    await aria_loop.startup()
    log.info("ARIA is fully online and ready to receive Telegram messages.")

def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        print("\n❌ ERROR: TELEGRAM_BOT_TOKEN is not set in your .env file.")
        print("To get a token:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow the instructions")
        print("3. Copy the token into your .env file")
        print("4. Run this script again\n")
        sys.exit(1)

    print("\n🚀 Starting ARIA Telegram Adapter...")
    
    # Security status
    allowed = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    public = telegram_public_mode_enabled()
    paired_users = settings_store.list_telegram_users()
    if allowed:
        print(f"🔒 Whitelist active: {allowed}")
    elif public:
        print("⚠️  PUBLIC MODE: Any Telegram user can interact with ARIA!")
    elif paired_users:
        print(f"🔒 Pairing active: {len(paired_users)} Telegram user(s) authorized.")
    else:
        print("🔒 Deny-by-default: generate a pairing code with `aria telegram pair` or set ALLOWED_TELEGRAM_USERS.")
    
    # Build the Telegram application
    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("pair", pair_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("approvals", approvals_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_message))

    # Start polling for messages
    app.run_polling()

if __name__ == '__main__':
    main()
