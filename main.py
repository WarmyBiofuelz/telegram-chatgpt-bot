import os
from dotenv import load_dotenv
import asyncio
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import logging

load_dotenv()

SYSTEM_PROMPT = (
    "You are a helpful AI assistant. You can help with general questions, "
    "conversations, and provide useful information. Be friendly and helpful."
)

# Use OpenAI's GPT-3.5 model (original version)
api_key = os.getenv("OPENAI_API_KEY")
model = "gpt-3.5-turbo"

client = AsyncOpenAI(
    api_key=api_key
)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! I'm a ChatGPT-powered bot. How can I help you today?"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "I can help you with:\n"
        "• General questions and conversations\n"
        "• Information and explanations\n"
        "• Creative writing and ideas\n\n"
        "Just send me any message!"
    )

async def get_chatgpt_response(user_message, conversation_history=None):
    """Get response from ChatGPT using OpenAI's GPT-3.5."""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # Add conversation history if available
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Get response from OpenAI
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"ChatGPT error: {e}", exc_info=True)
        return "Sorry, I couldn't process your request right now. Please try again later."

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages using ChatGPT."""
    user_message = update.message.text
    
    # Initialize conversation history for this user if not exists
    user_id = update.effective_user.id
    if not hasattr(context.bot_data, 'conversations'):
        context.bot_data['conversations'] = {}
    if user_id not in context.bot_data['conversations']:
        context.bot_data['conversations'][user_id] = []
    
    try:
        # Get ChatGPT response
        response_text = await get_chatgpt_response(user_message, context.bot_data['conversations'][user_id])
        
        # Add user message and response to conversation history
        context.bot_data['conversations'][user_id].append({"role": "user", "content": user_message})
        context.bot_data['conversations'][user_id].append({"role": "assistant", "content": response_text})
        
        # Keep only last 10 messages to prevent context from getting too long
        if len(context.bot_data['conversations'][user_id]) > 10:
            context.bot_data['conversations'][user_id] = context.bot_data['conversations'][user_id][-10:]
        
        # Handle Telegram message length limit
        if len(response_text) > 4096:
            response_text = response_text[:4093] + "..."
            
    except Exception as e:
        logger.error(f"Error in chatgpt_reply: {e}", exc_info=True)
        response_text = "Sorry, I couldn't process your request right now. Please try again later."
    
    await update.message.reply_text(response_text)

async def main():
    """Start the Telegram bot."""
    # Check for required API keys
    if not os.getenv('TELEGRAM_BOT_TOKEN') or not api_key:
        logger.error("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment.")
        return

    # Build the application
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

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
    # Simple approach for basic ChatGPT bot
    asyncio.run(main()) 