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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! I'm a ChatGPT-powered bot with web search capabilities. "
        "Send me a message and I'll reply using OpenAI's GPT-4 with real-time web search when needed!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "I can help you with:\n"
        "• General questions and conversations\n"
        "• Real-time information from the web\n"
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
    """Handle incoming messages: send them to OpenAI and reply with the result."""
    user_message = update.message.text
    try:
        # Detect language
        try:
            lang = detect(user_message)
        except LangDetectException:
            lang = "en"  # fallback

        # Map language codes to language names for the system prompt
        lang_map = {
            "lt": "Lietuvių",  # Lithuanian
            "lv": "Latviešu",  # Latvian
            "en": "English",
            # add more if needed
        }
        language_name = lang_map.get(lang, "English")

        # Detect if web search is needed
        search_keywords = [
            'weather', 'news', 'today', 'latest', 'current', 'price', 'stock',
            'weather', 'naujienos', 'šiandien', 'naujausi', 'dabartiniai', 'kaina', 'akcijos',  # Lithuanian
            'laiks', 'jaunumi', 'šodien', 'jaunākie', 'pašreizējie', 'cena', 'akcijas'  # Latvian
        ]
        
        # Check for question patterns first (more aggressive search for people/topics)
        search_patterns = [
            'who is', 'what is', 'who are', 'what are',
            'kas yra', 'kas tai', 'kas yra', 'kas tai',  # Lithuanian
            'kas ir', 'kas tas', 'kas ir', 'kas tas'     # Latvian
        ]
        
        # More comprehensive search detection
        needs_search = any(pattern in user_message.lower() for pattern in search_patterns)
        
        # If no question pattern, check for other keywords
        if not needs_search:
            needs_search = any(keyword in user_message.lower() for keyword in search_keywords)

        # Enhanced system prompt
        system_prompt = f"""You are a helpful assistant. Respond in {language_name} language.

Your knowledge is mostly limited to the end of 2023, and now it is 2025. 
When provided with recent web search results, use them to give accurate and up-to-date information.
If no search results are provided, answer based on your training data.

IMPORTANT: If you don't have current information and search results are provided, use them to answer the question.
Do not ask users to search - just use the search results that are provided to you.

Always respond in {language_name} language."""

        if needs_search:
            # Do web search automatically
            await update.message.reply_text("🔍 Searching for current information...")
            try:
                search_results = web_search(user_message)
                if search_results and search_results != "No results found.":
                    # Include search results in the prompt
                    enhanced_message = f"User question: {user_message}\n\nRecent web search results: {search_results}"
                else:
                    enhanced_message = user_message
            except Exception as e:
                logger.error(f"Web search error: {e}")
                enhanced_message = user_message
        else:
            enhanced_message = user_message

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enhanced_message}
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