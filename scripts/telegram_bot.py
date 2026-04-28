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
from aria.utils.logger import setup_logger

log = setup_logger("aria.telegram")

# Global singleton for the Cognitive Loop
aria_loop = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    user_id = update.effective_user.id
    await update.message.reply_text(
        "👋 Hello! I am ARIA (Adaptive Reasoning & Intelligence Architecture).\n\n"
        "My cognitive engine is online. I have access to your tools, memory, "
        "and knowledge graph. How can I help you today?\n\n"
        f"Your Telegram ID: `{user_id}`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pass incoming Telegram messages into ARIA's Cognitive Loop."""
    user_text = update.message.text
    if not user_text:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # -------------------------------------------------------------------------
    # SECURITY: Whitelist Check (deny-by-default)
    # -------------------------------------------------------------------------
    allowed_users_env = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    public_mode = os.getenv("TELEGRAM_PUBLIC_MODE", "false").lower() == "true"
    
    if not allowed_users_env and not public_mode:
        # No whitelist set AND not explicitly public → DENY
        log.warning(f"Access denied for User ID {user_id}: ALLOWED_TELEGRAM_USERS is not configured.")
        await update.message.reply_text(
            f"🔒 **Bot Not Configured**\n\n"
            f"This ARIA instance has no authorized users set.\n"
            f"Your Telegram ID: `{user_id}`\n\n"
            f"The owner must add this ID to `ALLOWED_TELEGRAM_USERS` in the `.env` file.\n"
            f"Or set `TELEGRAM_PUBLIC_MODE=true` to allow all users.",
            parse_mode="Markdown"
        )
        return
    
    if allowed_users_env:
        try:
            allowed_users = [int(x.strip()) for x in allowed_users_env.split(",") if x.strip()]
        except ValueError:
            log.error("ALLOWED_TELEGRAM_USERS contains non-integer values!")
            return
            
        if allowed_users and user_id not in allowed_users:
            log.warning(f"Unauthorized access attempt from User ID: {user_id}")
            await update.message.reply_text(
                f"🚫 **Access Denied**\n\n"
                f"You are not authorized to use this ARIA instance.\n"
                f"Your Telegram ID: `{user_id}`\n\n"
                f"If you are the owner, add this ID to `ALLOWED_TELEGRAM_USERS` in the `.env` file.",
                parse_mode="Markdown"
            )
            return
        
    # Show "typing..." indicator while ARIA thinks
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    try:
        # Route the message into the core agent loop!
        cognitive = await aria_loop.process(user_text)
        
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
    public = os.getenv("TELEGRAM_PUBLIC_MODE", "false").lower() == "true"
    if allowed:
        print(f"🔒 Whitelist active: {allowed}")
    elif public:
        print("⚠️  PUBLIC MODE: Any Telegram user can interact with ARIA!")
    else:
        print("🔒 Deny-by-default: Set ALLOWED_TELEGRAM_USERS in .env to authorize users.")
    
    # Build the Telegram application
    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling for messages
    app.run_polling()

if __name__ == '__main__':
    main()
