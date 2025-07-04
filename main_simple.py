import sys
if sys.version_info >= (3, 10):
    import nest_asyncio
    nest_asyncio.apply()
import os
import logging
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import AsyncOpenAI
from duckduckgo_search import DDGS

load_dotenv()

SYSTEM_PROMPT = (
    "Your knowledge is mostly limited to the end of 2023, and now it is 2025. "
    "When answering questions involving current events, recent data, or real-time updates, ALWAYS use the web_search tool (DuckDuckGo) to find accurate and up-to-date information. "
    "If you are unsure or do not have the information, use the web_search tool to look it up online. "
    "Do not guess or answer from your own knowledge for current or factual questions—always use the web_search tool. "
    "Example:\n"
    "User: What is the date today?\n"
    "Assistant: [uses web_search tool to find the current date]\n"
    "Whenever needed, use the web_search tool to find the latest information."
)

api_key = os.getenv("SECRET2")
endpoint = "https://models.github.ai/inference"
model = "openai/gpt-4.1-nano"

client = AsyncOpenAI(
    base_url=endpoint,
    api_key=api_key
)

# Rate limiting for DuckDuckGo
last_search_time = 0
SEARCH_COOLDOWN = 5  # seconds between searches

def web_search(query: str) -> str:
    """Search for information on the internet using DuckDuckGo with rate limiting."""
    global last_search_time
    
    # Rate limiting
    current_time = time.time()
    if current_time - last_search_time < SEARCH_COOLDOWN:
        time.sleep(SEARCH_COOLDOWN - (current_time - last_search_time))
    
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, region="wt-wt", safesearch="off", max_results=3)
            snippets = [r["body"] for r in results if "body" in r]
            last_search_time = time.time()
            return "\n".join(snippets) if snippets else "No results found."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        last_search_time = time.time()
        # If it's a rate limit error, wait longer before next search
        if "Ratelimit" in str(e):
            time.sleep(10)  # Wait 10 seconds after rate limit
        return "Search temporarily unavailable. Please try again in a moment."

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! I'm a ChatGPT-powered bot with automatic web search capabilities. "
        "I'll automatically search for current information when needed!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "I can help you with:\n"
        "• General questions and conversations\n"
        "• Real-time information from the web (automatic)\n"
        "• Current events and latest news\n\n"
        "Just send me any message!"
    )

async def get_agent_response(user_message):
    """Simulate the agents framework behavior with automatic web search."""
    # Always search for current information
    search_results = web_search(user_message)
    
    # Create the conversation with search results
    if search_results and search_results != "No results found." and "temporarily unavailable" not in search_results:
        conversation = f"""User: {user_message}

Recent web search results: {search_results}

Please answer the user's question using the search results if they are relevant, or your knowledge if not."""
    else:
        conversation = f"User: {user_message}"
    
    # Send to GitHub model
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": conversation}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages using the agent with automatic web search."""
    user_message = update.message.text
    try:
        # Get agent response with automatic web search
        response_text = await get_agent_response(user_message)
        
        # Handle Telegram message length limit
        if len(response_text) > 4096:
            response_text = response_text[:4093] + "..."
            
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        response_text = "Sorry, I couldn't process your request right now. Please try again later."
    
    await update.message.reply_text(response_text)

async def main():
    """Start the Telegram bot."""
    # Check for required API keys
    if not os.getenv('TELEGRAM_BOT_TOKEN') or not api_key:
        logger.error("Missing TELEGRAM_BOT_TOKEN or SECRET2 in environment.")
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
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise 