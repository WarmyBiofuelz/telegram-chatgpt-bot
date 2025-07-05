import sys
import os
import logging
import asyncio
from telegram.ext import ApplicationBuilder
from shared.config import TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL

# Import modules
from modules.chat_module import get_chat_handlers
from modules.calendar_module import get_calendar_handlers

# Set up logging
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

async def main():
    """Start the Telegram bot."""
    # Check for required API keys
    if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
        logger.error("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment.")
        return

    # Build the application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register all handlers from modules
    chat_handlers = get_chat_handlers()
    calendar_handlers = get_calendar_handlers()
    
    # Add all handlers to the application
    for handler in chat_handlers + calendar_handlers:
        app.add_handler(handler)

    # Start the bot
    logger.info("Bot is starting with chat and calendar modules...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise 