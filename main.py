import sys
if sys.version_info >= (3, 10):
    import nest_asyncio
    nest_asyncio.apply()
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize the OpenAI client
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.openai.com/v1"
)

# Set up logging for debugging and monitoring
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! I'm a ChatGPT-powered bot. Send me a message and I'll reply using OpenAI's GPT-4!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "Just send me any message and I'll respond with ChatGPT!"
    )

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages: send them to OpenAI and reply with the result."""
    user_message = update.message.text
    try:
        # Add a system prompt for Lithuanian (optional, remove if not needed)
        messages = [
            {"role": "system", "content": "Atsakyk tik lietuvių kalba, nepriklausomai nuo klausimo kalbos. Jei klausimas užduotas kita kalba, vis tiek atsakyk lietuviškai."},
            {"role": "user", "content": user_message}
        ]
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        bot_reply = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}", exc_info=True)
        bot_reply = "Sorry, I couldn't process your request right now. Please try again later."
    await update.message.reply_text(bot_reply)

async def main():
    """Start the Telegram bot."""
    # Check for required API keys
    if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
        logger.error("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment.")
        return

    # Build the application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Register message handler for all text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_reply))

    # Start the bot
    logger.info("Bot is starting...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise 