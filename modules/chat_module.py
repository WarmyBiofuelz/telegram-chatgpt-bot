import sys
import os
import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from shared.config import OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL

# Import knowledge base (try advanced first, fallback to simple)
try:
    from modules.advanced_knowledge_module import get_advanced_knowledge_context_for_chat
    KNOWLEDGE_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Using advanced RAG knowledge system")
except ImportError:
    try:
        from modules.knowledge_module import get_knowledge_context_for_chat
        KNOWLEDGE_AVAILABLE = True
        logger = logging.getLogger(__name__)
        logger.info("Using simple knowledge system")
    except ImportError:
        KNOWLEDGE_AVAILABLE = False
        logger = logging.getLogger(__name__)
        logger.warning("No knowledge system available")

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
    knowledge_info = ""
    if KNOWLEDGE_AVAILABLE:
        knowledge_info = "\n• Company policies and procedures\n• Product information\n• FAQ answers\n• Driver information\n\nUse /ask <question> for advanced knowledge search!"
    
    await update.message.reply_text(
        f"Hello! I'm a ChatGPT-powered bot with company knowledge.\n\n"
        f"I can help you with:\n"
        f"• General questions and conversations{knowledge_info}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    knowledge_commands = ""
    if KNOWLEDGE_AVAILABLE:
        knowledge_commands = "\n📚 Knowledge:\n• /ask <question> - Advanced knowledge search\n• /reload_advanced_knowledge - Reload knowledge (admin)\n"
    
    await update.message.reply_text(
        f"🤖 Bot Commands:\n\n"
        f"💬 Chat:\n"
        f"• Send any message for ChatGPT response\n"
        f"• I'll answer in Lithuanian and automatically use company knowledge\n"
        f"• I can recognize drivers by phone number{knowledge_commands}\n"
        f"📅 Calendar:\n"
        f"• /calendar_today - Today's events\n"
        f"• /calendar_week - This week's events\n"
        f"• /calendar_next - Next meeting\n\n"
        f"Just send me any message and I'll respond with ChatGPT!"
    )

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages: send them to OpenAI and reply with the result."""
    user_message = update.message.text
    
    try:
        # Get relevant knowledge context (includes driver information)
        knowledge_context = ""
        if KNOWLEDGE_AVAILABLE:
            try:
                from modules.advanced_knowledge_module import get_advanced_knowledge_context_for_chat
                knowledge_context = get_advanced_knowledge_context_for_chat(user_message)
            except ImportError:
                try:
                    from modules.knowledge_module import get_knowledge_context_for_chat
                    knowledge_context = get_knowledge_context_for_chat(user_message)
                except ImportError:
                    knowledge_context = ""
        
        # Prepare system prompt with knowledge integration
        system_prompt = (
            "Atsakyk tik lietuvių kalba, nepriklausomai nuo klausimo kalbos. "
            "Jei klausimas užduotas kita kalba, vis tiek atsakyk lietuviškai. "
            "Atsakyk tik tuo, ką žinai iš savo žinių. "
            "Jei neturi informacijos apie klausimą, atsakyk: 'Atsiprašau, bet neturiu informacijos apie tai.' "
            "Nekurk informacijos, jei jos nežinai. "
            "Jei žinutėje yra telefono numeris ir tu gali identifikuoti vairuotoją, atsakyk kaip bendraudamas su tuo vairuotoju."
        )
        
        # Add knowledge context if available
        if knowledge_context and knowledge_context.strip():
            system_prompt += f"\n\nPapildoma informacija iš įmonės žinių bazės:\n{knowledge_context}\n\nNaudok šią informaciją, jei ji atitinka klausimą."
        
        messages = [
            {"role": "system", "content": system_prompt},
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