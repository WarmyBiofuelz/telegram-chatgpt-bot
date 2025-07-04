import sys
if sys.version_info >= (3, 10):
    import nest_asyncio
    nest_asyncio.apply()
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import AsyncOpenAI
from agents import Agent, Runner, ModelSettings, OpenAIChatCompletionsModel, function_tool
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

model_instance = OpenAIChatCompletionsModel(
    model=model,
    openai_client=client
)

import time

# Global rate limiting for DuckDuckGo
last_search_time = 0
SEARCH_COOLDOWN = 10  # seconds between searches

@function_tool
def web_search(query: str) -> str:
    """Ieškok informacijos internete naudodamas DuckDuckGo."""
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
            return "\n".join(snippets) if snippets else "Nerasta rezultatų."
    except Exception as e:
        last_search_time = time.time()
        # If it's a rate limit error, wait longer
        if "Ratelimit" in str(e):
            time.sleep(30)  # Wait 30 seconds after rate limit
        return "Search temporarily unavailable due to rate limits. Please try again in a few minutes."

tools = [web_search]

agent = Agent(
    name="Assistant",
    instructions=SYSTEM_PROMPT,
    model=model_instance,
    model_settings=ModelSettings(temperature=0.1),
    tools=tools
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

async def get_agent_response(messages):
    """Get response from the agent using the same approach as the working Streamlit code."""
    try:
        # Compose the conversation for the agent
        conversation = ""
        for msg in messages:
            if msg["role"] == "user":
                conversation += f"User: {msg['content']}\n"
            elif msg["role"] == "assistant":
                conversation += f"Assistant: {msg['content']}\n"
        # Run the agent and get the response
        result = await Runner.run(agent, conversation)
        return result.final_output
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        return "Sorry, I couldn't process your request right now. Please try again later."

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages using the agent."""
    user_message = update.message.text
    
    # Initialize conversation history for this user if not exists
    user_id = update.effective_user.id
    if not hasattr(context.bot_data, 'conversations'):
        context.bot_data['conversations'] = {}
    if user_id not in context.bot_data['conversations']:
        context.bot_data['conversations'][user_id] = []
    
    # Add user message to conversation history
    context.bot_data['conversations'][user_id].append({"role": "user", "content": user_message})
    
    try:
        # Get agent response with conversation history
        response_text = await get_agent_response(context.bot_data['conversations'][user_id])
        
        # Add assistant response to conversation history
        context.bot_data['conversations'][user_id].append({"role": "assistant", "content": response_text})
        
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
    # Simple approach without nest_asyncio complications
    asyncio.run(main()) 