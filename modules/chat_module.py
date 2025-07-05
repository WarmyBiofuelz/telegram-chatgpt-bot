import sys
import os
import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from shared.config import OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL

# Set up logging
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize the OpenAI client
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.openai.com/v1"
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        # Add a system prompt for Lithuanian with knowledge limitation
        messages = [
            {"role": "system", "content": "Atsakyk tik lietuvių kalba, nepriklausomai nuo klausimo kalbos. Jei klausimas užduotas kita kalba, vis tiek atsakyk lietuviškai. Atsakyk tik tuo, ką žinai iš savo žinių. Jei neturi informacijos apie klausimą, atsakyk: 'Atsiprašau, bet neturiu informacijos apie tai.' Nekurk informacijos, jei jos nežinai."},
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

def get_chat_handlers():
    """Return chat-related command and message handlers."""
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_reply)
    ] 