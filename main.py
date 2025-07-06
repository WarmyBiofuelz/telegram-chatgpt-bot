import sys
import os
import logging
import asyncio

# Handle nest_asyncio for environments with existing event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram.ext import ApplicationBuilder
from shared.config import TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL

# Import modules
from modules.chat_module import get_chat_handlers
from modules.calendar_module import get_calendar_handlers
from modules.knowledge_module import get_knowledge_handlers

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
    knowledge_handlers = get_knowledge_handlers()
    
    # Add all handlers to the application
    for handler in chat_handlers + calendar_handlers + knowledge_handlers:
        app.add_handler(handler)

    # Start the bot
    logger.info("Bot is starting with chat, calendar, and knowledge modules...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e) or "Cannot close a running event loop" in str(e):
            # Fallback for environments with existing event loops
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise 