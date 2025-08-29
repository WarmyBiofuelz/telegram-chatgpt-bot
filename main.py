import logging
import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta

# Handle nest_asyncio for environments with existing event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from shared.config import (
    TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL,
    RATE_LIMIT_SECONDS, MAX_RETRIES, RETRY_DELAY, OPENAI_TIMEOUT,
    MAX_TOKENS, TEMPERATURE
)
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError

# Set up logging once
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Global OpenAI client with optimized settings
client = None

# Rate limiting and user management
user_last_message = defaultdict(float)

class BotMetrics:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.average_response_time = 0
        self.start_time = time.time()
    
    def record_request(self, success: bool, response_time: float):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Update average response time
        if self.average_response_time == 0:
            self.average_response_time = response_time
        else:
            self.average_response_time = (self.average_response_time + response_time) / 2
    
    def get_stats(self):
        uptime = time.time() - self.start_time
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        return {
            'uptime_hours': uptime / 3600,
            'total_requests': self.total_requests,
            'success_rate': f"{success_rate:.1f}%",
            'avg_response_time': f"{self.average_response_time:.2f}s"
        }

# Initialize metrics
metrics = BotMetrics()

def initialize_openai_client():
    """Initialize OpenAI client with optimized settings."""
    global client
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
            timeout=OPENAI_TIMEOUT,
            max_retries=2   # Built-in retry logic
        )
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        raise

def is_rate_limited(user_id: int) -> bool:
    """Check if user is rate limited."""
    current_time = time.time()
    last_message_time = user_last_message.get(user_id, 0)
    
    if current_time - last_message_time < RATE_LIMIT_SECONDS:
        return True
    
    user_last_message[user_id] = current_time
    return False

async def start_command(update, context):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! I'm a ChatGPT-powered bot.\n\n"
        "I can help you with general questions and conversations.\n"
        "Just send me any message and I'll respond!"
    )

async def help_command(update, context):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "🤖 Bot Commands:\n\n"
        "💬 Chat:\n"
        "• Send any message for ChatGPT response\n"
        "• I'll answer your questions and chat with you\n\n"
        "📊 Stats:\n"
        "• /stats - View bot statistics\n\n"
        "Just send me any message and I'll respond with ChatGPT!"
    )

async def stats_command(update, context):
    """Show bot statistics (admin feature)."""
    stats = metrics.get_stats()
    stats_message = (
        "📊 Bot Statistics:\n\n"
        f"⏱️ Uptime: {stats['uptime_hours']:.1f} hours\n"
        f"📝 Total Requests: {stats['total_requests']}\n"
        f"✅ Success Rate: {stats['success_rate']}\n"
        f"⚡ Avg Response Time: {stats['avg_response_time']}"
    )
    await update.message.reply_text(stats_message)

async def chatgpt_reply(update, context):
    """Handle incoming messages: send them to OpenAI and reply with the result."""
    user_id = update.effective_user.id
    user_message = update.message.text
    start_time = time.time()
    
    # Rate limiting check
    if is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Please wait a moment before sending another message. "
            f"Rate limit: {RATE_LIMIT_SECONDS} seconds between messages."
        )
        return
    
    try:
        # Prepare system prompt
        system_prompt = (
            "You are a helpful and friendly AI assistant. "
            "Respond naturally and helpfully to user messages. "
            "Keep responses concise but informative."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Make API call with retry logic
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE
                )
                break
            except RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                else:
                    raise
            except (APIError, APIConnectionError) as e:
                logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                else:
                    raise
        
        if response:
            bot_reply = response.choices[0].message.content.strip()
            response_time = time.time() - start_time
            metrics.record_request(True, response_time)
            logger.info(f"User {user_id}: Response in {response_time:.2f}s")
        else:
            raise Exception("No response received from OpenAI")
        
    except RateLimitError:
        bot_reply = "🚫 Rate limit exceeded. Please try again in a few minutes."
        metrics.record_request(False, time.time() - start_time)
        logger.warning(f"Rate limit hit for user {user_id}")
    except (APIError, APIConnectionError) as e:
        bot_reply = "🔌 Service temporarily unavailable. Please try again later."
        metrics.record_request(False, time.time() - start_time)
        logger.error(f"OpenAI API error for user {user_id}: {e}")
    except Exception as e:
        bot_reply = "❌ An unexpected error occurred. Please try again later."
        metrics.record_request(False, time.time() - start_time)
        logger.error(f"Unexpected error for user {user_id}: {e}", exc_info=True)
    
    await update.message.reply_text(bot_reply)

async def main():
    """Start the Telegram bot."""
    # Check for required API keys
    if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
        logger.error("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment.")
        return

    # Initialize OpenAI client
    initialize_openai_client()

    # Build the application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_reply))

    # Start the bot
    logger.info("Bot is starting with optimized chat functionality...")
    
    try:
        await app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
    finally:
        logger.info("Bot shutdown complete")

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