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
from langdetect import detect, LangDetectException
from agents import Agent, Runner, ModelSettings, OpenAIChatCompletionsModel, function_tool
from duckduckgo_search import DDGS

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

@function_tool
def web_search(query: str) -> str:
    """Search for information on the internet using DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, region="wt-wt", safesearch="off", max_results=3)
            snippets = [r["body"] for r in results if "body" in r]
            return "\n".join(snippets) if snippets else "No results found."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return "Search failed. Please try again."

# Create the agent with web search tool
tools = [web_search]

agent = Agent(
    name="Assistant",
    instructions="""Your knowledge is mostly limited to the end of 2023, and now it is 2025. 
When answering questions involving current events, recent data, or real-time updates, ALWAYS use the web_search tool (DuckDuckGo) to find accurate and up-to-date information. 
If you are unsure or do not have the information, use the web_search tool to look it up online. 
Do not guess or answer from your own knowledge for current or factual questions—always use the web_search tool.
Respond in the same language as the user's question.""",
    model=client,
    model_settings=ModelSettings(temperature=0.1),
    tools=tools
)

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
        "• Multi-language support (I'll reply in your language)\n"
        "• Current events and latest news\n\n"
        "Just send me any message!"
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command for direct web search."""
    if not context.args:
        await update.message.reply_text("Usage: /search <your search query>")
        return
    
    query = ' '.join(context.args)
    await update.message.reply_text(f"Searching for: {query}")
    
    try:
        search_results = web_search(query)
        if len(search_results) > 4096:  # Telegram message limit
            search_results = search_results[:4093] + "..."
        await update.message.reply_text(search_results)
    except Exception as e:
        logger.error(f"Search command error: {e}")
        await update.message.reply_text("Sorry, search failed. Please try again.")

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages using the agent with automatic web search."""
    user_message = update.message.text
    try:
        # Use the agent to get response with automatic web search
        conversation = f"User: {user_message}"
        result = await Runner.run(agent, conversation)
        bot_reply = result.final_output
        
        # Handle Telegram message length limit
        if len(bot_reply) > 4096:
            bot_reply = bot_reply[:4093] + "..."
            
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
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
    app.add_handler(CommandHandler("search", search_command))

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