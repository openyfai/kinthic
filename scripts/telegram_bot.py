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
    await update.message.reply_text(
        "👋 Hello! I am ARIA (Adaptive Reasoning & Intelligence Architecture).\n\n"
        "My cognitive engine is online. I have access to your tools, memory, "
        "and knowledge graph. How can I help you today?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pass incoming Telegram messages into ARIA's Cognitive Loop."""
    user_text = update.message.text
    if not user_text:
        return

    chat_id = update.effective_chat.id
    
    # Show "typing..." indicator while ARIA thinks
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    try:
        # Route the message into the core agent loop!
        # This is the "Adapter Pattern" — Telegram is just an ingress channel.
        cognitive = await aria_loop.process(user_text)
        
        # Send the final response back to Telegram
        # We use Markdown formatting so ARIA's code blocks and lists render nicely
        await update.message.reply_text(
            cognitive.response, 
            parse_mode='Markdown'
        )
        
    except Exception as e:
        log.error(f"Error processing message: {e}")
        await update.message.reply_text(f"⚠️ **Internal Error:**\n`{str(e)}`", parse_mode='Markdown')

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
