import logging
import asyncio
import sqlite3
import schedule
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

from typing import Optional, Dict, Any

# Handle nest_asyncio for environments with existing event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from shared.config import (
    TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL,
    RATE_LIMIT_SECONDS, MAX_RETRIES, RETRY_DELAY, OPENAI_TIMEOUT,
    MAX_TOKENS, TEMPERATURE, OPENAI_MODEL
)
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError

# Set up logging
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Global OpenAI client
client = None

# Database setup with connection pooling
DB_PATH = "horoscope_users.db"
_db_connection = None

# Conversation states
(ASKING_NAME, ASKING_BIRTHDAY, ASKING_LANGUAGE, ASKING_PROFESSION, 
 ASKING_HOBBIES, ASKING_SEX, ASKING_INTERESTS) = range(7)

# Questions sequence with validation
QUESTIONS = [
    (ASKING_NAME, "name", "Koks tavo vardas?", lambda x: len(x.strip()) >= 2),
    (ASKING_BIRTHDAY, "birthday", "Kokia tavo gimimo data? (pvz.: 1979-05-04)", 
     lambda x: _validate_date(x)),
    (ASKING_LANGUAGE, "language", "Kokia kalba nori gauti horoskopą? (LT/EN/RU)", 
     lambda x: x.strip().upper() in ['LT', 'EN', 'RU']),
    (ASKING_PROFESSION, "profession", "Kokia tavo profesija?", lambda x: len(x.strip()) >= 2),
    (ASKING_HOBBIES, "hobbies", "Kokie tavo pomėgiai?", lambda x: len(x.strip()) >= 2),
    (ASKING_SEX, "sex", "Kokia tavo lytis? (moteris/vyras)", 
     lambda x: x.strip().lower() in ['moteris', 'vyras']),
    (ASKING_INTERESTS, "interests", "Kuo labiausiai domiesi? (pvz.: šeima, karjera, kelionės)", 
     lambda x: len(x.strip()) >= 2)
]

# Rate limiting cache
user_last_message = {}
user_states = {}

def _validate_date(date_str: str) -> bool:
    """Validate date format."""
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False

def get_db_connection():
    """Get database connection with optimizations."""
    global _db_connection
    if _db_connection is None:
        _db_connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db_connection.execute("PRAGMA journal_mode=WAL")
        _db_connection.execute("PRAGMA synchronous=NORMAL")
        _db_connection.execute("PRAGMA cache_size=10000")
        _db_connection.execute("PRAGMA temp_store=MEMORY")
    return _db_connection

def initialize_database():
    """Initialize SQLite database for user profiles with optimizations."""
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            birthday TEXT NOT NULL,
            language TEXT NOT NULL CHECK (language IN ('LT', 'EN', 'RU')),
            profession TEXT NOT NULL,
            hobbies TEXT NOT NULL,
            sex TEXT NOT NULL CHECK (sex IN ('moteris', 'vyras')),
            interests TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_horoscope_date DATE,
            is_active BOOLEAN DEFAULT 1
        )
        """)
        
        # Create indexes for better performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_last_horoscope ON users(last_horoscope_date)")
        
        conn.commit()
    logger.info("Database initialized successfully with optimizations")

def initialize_openai_client():
    """Initialize OpenAI client with optimizations."""
    global client
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
            timeout=OPENAI_TIMEOUT,
            max_retries=2
        )
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        raise

def is_rate_limited(user_id: int) -> bool:
    """Check if user is rate limited with cleanup."""
    current_time = time.time()
    
    # Clean old entries (older than 1 hour)
    cutoff_time = current_time - 3600
    user_last_message = {k: v for k, v in user_last_message.items() if v > cutoff_time}
    
    last_message_time = user_last_message.get(user_id, 0)
    
    if current_time - last_message_time < RATE_LIMIT_SECONDS:
        return True
    
    user_last_message[user_id] = current_time
    return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the horoscope bot registration process."""
    chat_id = update.effective_chat.id
    
    if is_rate_limited(chat_id):
        await update.message.reply_text(
            f"⏳ Palaukite {RATE_LIMIT_SECONDS} sekundės prieš siųsdami kitą žinutę."
        )
        return ConversationHandler.END
    
    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
    existing_user = cursor.fetchone()
    conn.commit()
    
    if existing_user:
        await update.message.reply_text(
            f"Labas, {existing_user[0]}! 🌟\n\n"
            "Tu jau esi užsiregistravęs! Gali:\n"
            "• /horoscope - Gauti šiandienos horoskopą\n"
            "• /profile - Peržiūrėti savo profilį\n"
            "• /update - Atnaujinti duomenis\n"
            "• /help - Pagalba"
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Labas! Aš esu tavo asmeninis horoskopų botukas 🌟\n\n"
        "Atsakyk į kelis klausimus, kad galėčiau pritaikyti horoskopą būtent tau.\n\n"
        "Pradėkime nuo tavo vardo:"
    )
    return ASKING_NAME

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_index: int):
    """Generic handler for all questions with validation."""
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    if is_rate_limited(chat_id):
        await update.message.reply_text(
            f"⏳ Palaukite {RATE_LIMIT_SECONDS} sekundės prieš siųsdami kitą žinutę."
        )
        return question_index
    
    _, field_name, question_text, validator = QUESTIONS[question_index]
    
    if not validator(user_input):
        error_messages = {
            ASKING_NAME: "Vardas turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            ASKING_BIRTHDAY: "Neteisingas datos formatas! Naudok formatą YYYY-MM-DD (pvz.: 1990-05-15):",
            ASKING_LANGUAGE: "Pasirink vieną iš: LT, EN arba RU:",
            ASKING_PROFESSION: "Profesija turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            ASKING_HOBBIES: "Pomėgiai turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            ASKING_SEX: "Pasirink: moteris arba vyras:",
            ASKING_INTERESTS: "Interesai turi būti bent 2 simbolių ilgio. Bandyk dar kartą:"
        }
        await update.message.reply_text(error_messages[question_index])
        return question_index
    
    # Store the validated input
    if field_name == "language":
        user_input = user_input.upper()
    elif field_name == "sex":
        user_input = user_input.lower()
    
    context.user_data[field_name] = user_input
    
    # Move to next question or complete registration
    next_index = question_index + 1
    if next_index < len(QUESTIONS):
        _, _, next_question, _ = QUESTIONS[next_index]
        await update.message.reply_text(f"Puiku! 🌟\n\n{next_question}")
        return next_index
    else:
        # Complete registration
        await complete_registration(update, context)
        return ConversationHandler.END

async def complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete user registration and save to database."""
    chat_id = update.effective_chat.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO users 
    (chat_id, name, birthday, language, profession, hobbies, sex, interests, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        chat_id,
        context.user_data['name'],
        context.user_data['birthday'],
        context.user_data['language'],
        context.user_data['profession'],
        context.user_data['hobbies'],
        context.user_data['sex'],
        context.user_data['interests']
    ))
    conn.commit()
    
    await update.message.reply_text(
        f"Puiku, {context.user_data['name']}! 🎉\n\n"
        "Tavo profilis sukurtas! Nuo šiol kiekvieną rytą 07:30 gausi savo asmeninį horoskopą! 🌞\n\n"
        "Gali naudoti:\n"
        "• /horoscope - Gauti šiandienos horoskopą\n"
        "• /profile - Peržiūrėti savo profilį\n"
        "• /update - Atnaujinti duomenis\n"
        "• /help - Pagalba"
    )
    
    context.user_data.clear()

# Question handlers
async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_NAME)

async def ask_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_BIRTHDAY)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_LANGUAGE)

async def ask_profession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_PROFESSION)

async def ask_hobbies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_HOBBIES)

async def ask_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_SEX)

async def ask_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_INTERESTS)

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the registration process."""
    await update.message.reply_text(
        "Registracija atšaukta. Jei nori pradėti iš naujo, naudok /start"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def get_horoscope_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get today's horoscope for the user."""
    chat_id = update.effective_chat.id
    
    if is_rate_limited(chat_id):
        await update.message.reply_text(
            f"⏳ Palaukite {RATE_LIMIT_SECONDS} sekundės prieš siųsdami kitą žinutę."
        )
        return
    
    # Get user data
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
    user = cursor.fetchone()
    conn.commit()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date, is_active = user
    
    # Check if user already got horoscope today
    today = datetime.now().date()
    if last_horoscope_date and datetime.strptime(last_horoscope_date, "%Y-%m-%d").date() == today:
        await update.message.reply_text(
            f"Labas, {name}! 🌟\n\n"
            "Tu jau gavai šiandienos horoskopą! Rytą 07:30 gausi naują. 🌞"
        )
        return
    
    # Generate horoscope
    await update.message.reply_text("Generuoju tavo asmeninį horoskopą... ✨")
    
    try:
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex, interests)
        
        # Update last horoscope date
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?",
            (today.strftime("%Y-%m-%d"), chat_id)
        )
        conn.commit()
        
        await update.message.reply_text(horoscope)
        
    except Exception as e:
        logger.error(f"Error generating horoscope for user {chat_id}: {e}")
        await update.message.reply_text(
            "Atsiprašau, įvyko klaida generuojant horoskopą. Bandyk vėliau."
        )

async def generate_horoscope(name: str, birthday: str, language: str, profession: str, 
                           hobbies: str, sex: str, interests: str) -> str:
    """Generate personalized horoscope using OpenAI with caching."""
    # Create optimized prompt based on language
    prompts = {
        "LT": f"""Sukurk asmeninį dienos horoskopą {name} ({sex}), gimusiam {birthday}.

Asmeninė informacija:
- Profesija: {profession}
- Pomėgiai: {hobbies}
- Interesai: {interests}

Horoskopo reikalavimai:
- Analizuok asmeninę informaciją ir sukurk logišką, asmenišką pranešimą
- Būk motyvuojantis, bet realistiškas
- Pateik praktišką patarimą, susijusį su jų gyvenimo situacija
- Naudok psichologinį supratimą apie žmogų
- Pridėk šiek tiek humoro, bet išlaikyk profesionalumą
- Būk originalus ir šviežias - nepasikartok
- 4-5 sakiniai, gerai suformuluoti

Sukurk horoskopą, kuris atitiktų šio žmogaus asmenybę ir gyvenimo situaciją.""",
        
        "EN": f"""Create a personalized daily horoscope for {name} ({sex}), born on {birthday}.

Personal information:
- Profession: {profession}
- Hobbies: {hobbies}
- Interests: {interests}

Horoscope requirements:
- Analyze the personal information and create a logical, personalized message
- Be motivating but realistic
- Provide practical advice related to their life situation
- Use psychological understanding about the person
- Add some humor while maintaining professionalism
- Be original and fresh - don't repeat
- 4-5 well-formulated sentences

Create a horoscope that matches this person's personality and life situation.""",
        
        "RU": f"""Создай персональный дневной гороскоп для {name} ({sex}), родившегося {birthday}.

Личная информация:
- Профессия: {profession}
- Хобби: {hobbies}
- Интересы: {interests}

Требования к гороскопу:
- Проанализируй личную информацию и создай логичное, персональное сообщение
- Будь мотивирующим, но реалистичным
- Дай практический совет, связанный с их жизненной ситуацией
- Используй психологическое понимание о человеке
- Добавь немного юмора, сохраняя профессионализм
- Будь оригинальным и свежим - не повторяйся
- 4-5 хорошо сформулированных предложений

Создай гороскоп, который соответствует личности и жизненной ситуации этого человека."""
    }
    
    prompt = prompts.get(language, prompts["LT"])
    
    # Make API call with optimized retry logic
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )
            return response.choices[0].message.content.strip()
            
        except RateLimitError:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
                continue
            else:
                raise
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
                continue
            else:
                raise

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's profile."""
    chat_id = update.effective_chat.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
    user = cursor.fetchone()
    conn.commit()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date, is_active = user
    
    profile_text = f"""
👤 **Tavo profilis:**

🌟 **Vardas:** {name}
📅 **Gimimo data:** {birthday}
🌍 **Kalba:** {language}
💼 **Profesija:** {profession}
🎨 **Pomėgiai:** {hobbies}
👤 **Lytis:** {sex}
❤️ **Interesai:** {interests}
📅 **Registracijos data:** {created_at}
"""
    
    if last_horoscope_date:
        profile_text += f"📊 **Paskutinis horoskopas:** {last_horoscope_date}"
    
    await update.message.reply_text(profile_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = """
🌟 **Horoskopų Botas - Pagalba**

**Komandos:**
• /start - Pradėti registraciją
• /horoscope - Gauti šiandienos horoskopą
• /profile - Peržiūrėti savo profilį
• /test_horoscope - Testuoti horoskopo generavimą
• /help - Ši pagalba

**Kaip veikia:**
1. Užsiregistruok su /start
2. Atsakyk į klausimus
3. Gauk asmeninį horoskopą kiekvieną rytą 07:30
4. Naudok /horoscope, kad gautum horoskopą bet kada

**Funkcijos:**
✨ Asmeniški horoskopai pagal tavo duomenis
🌍 Palaiko LT, EN, RU kalbas
📅 Automatinis siuntimas kiekvieną rytą
🎯 Motyvuojantys ir pozityvūs pranešimai
"""
    await update.message.reply_text(help_text)

async def test_horoscope_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test horoscope generation for debugging."""
    chat_id = update.effective_chat.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
    user = cursor.fetchone()
    conn.commit()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date, is_active = user
    
    await update.message.reply_text("🧪 Testuoju horoskopo generavimą...")
    
    try:
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex, interests)
        await update.message.reply_text(f"✅ **Testinis horoskopas:**\n\n{horoscope}")
    except Exception as e:
        logger.error(f"Test horoscope error for user {chat_id}: {e}")
        await update.message.reply_text(f"❌ Klaida: {str(e)}")

async def send_daily_horoscopes():
    """Send daily horoscopes to all registered users with optimizations."""
    logger.info("Starting daily horoscope sending...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE is_active = 1")
    all_users = cursor.fetchall()
    conn.commit()
    
    if not all_users:
        logger.info("No users found for daily horoscopes")
        return
    
    logger.info(f"Found {len(all_users)} users for daily horoscopes")
    
    # Get the bot instance from the application
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Process users in batches to avoid overwhelming the API
    batch_size = 10
    for i in range(0, len(all_users), batch_size):
        batch = all_users[i:i + batch_size]
        
        # Process batch concurrently
        tasks = []
        for user in batch:
            chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date, is_active = user
            task = send_horoscope_to_user(bot, user)
            tasks.append(task)
        
        # Wait for batch to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Small delay between batches
        if i + batch_size < len(all_users):
            await asyncio.sleep(1)

async def send_horoscope_to_user(bot, user):
    """Send horoscope to a single user."""
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date, is_active = user
    
    try:
        # Generate horoscope
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex, interests)
        
        # Send horoscope
        await bot.send_message(chat_id=chat_id, text=horoscope)
        
        # Update last horoscope date
        today = datetime.now().date()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?",
            (today.strftime("%Y-%m-%d"), chat_id)
        )
        conn.commit()
        
        logger.info(f"Sent horoscope to {name} (chat_id: {chat_id})")
        
    except Exception as e:
        logger.error(f"Failed to send horoscope to {name} (chat_id: {chat_id}): {e}")

def schedule_horoscopes():
    """Schedule daily horoscope sending with improved error handling."""
    def run_async_horoscopes():
        try:
            asyncio.run(send_daily_horoscopes())
        except Exception as e:
            logger.error(f"Error in scheduled horoscope sending: {e}")
    
    schedule.every().day.at("07:30").do(run_async_horoscopes)
    logger.info("Daily horoscopes scheduled for 07:30")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
            time.sleep(60)

async def main():
    """Start the horoscope bot with optimizations."""
    # Check for required API keys
    if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
        logger.error("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment.")
        return

    # Initialize database and OpenAI client
    initialize_database()
    initialize_openai_client()

    # Build the application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Create conversation handler for registration
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASKING_BIRTHDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_birthday)],
            ASKING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_language)],
            ASKING_PROFESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_profession)],
            ASKING_HOBBIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_hobbies)],
            ASKING_SEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sex)],
            ASKING_INTERESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_interests)],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
    )

    # Add handlers
    app.add_handler(registration_handler)
    app.add_handler(CommandHandler("horoscope", get_horoscope_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("test_horoscope", test_horoscope_command))
    app.add_handler(CommandHandler("help", help_command))

    # Start scheduler in a separate thread
    scheduler_thread = threading.Thread(target=schedule_horoscopes, daemon=True)
    scheduler_thread.start()

    # Start the bot
    logger.info("Optimized horoscope bot is starting...")
    
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
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise