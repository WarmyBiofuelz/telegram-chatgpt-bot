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

# Conversation states (reordered: Language first, then Name, Sex, Birthday, Profession, Hobbies)
(ASKING_LANGUAGE, ASKING_NAME, ASKING_SEX, ASKING_BIRTHDAY, ASKING_PROFESSION, 
 ASKING_HOBBIES) = range(6)

# Questions sequence with validation (reordered: Language first)
QUESTIONS = [
    (ASKING_LANGUAGE, "language", "Kokia kalba nori gauti horoskopą? (LT/EN/RU/LV)", 
     lambda x: x.strip().upper() in ['LT', 'EN', 'RU', 'LV']),
    (ASKING_NAME, "name", "Koks tavo vardas?", lambda x: len(x.strip()) >= 2),
    (ASKING_SEX, "sex", "Kokia tavo lytis? (moteris/vyras)", 
     lambda x: x.strip().lower() in ['moteris', 'vyras']),
    (ASKING_BIRTHDAY, "birthday", "Kokia tavo gimimo data? (pvz.: 1979-05-04)", 
     lambda x: _validate_date(x)),
    (ASKING_PROFESSION, "profession", "Kokia tavo profesija?", lambda x: len(x.strip()) >= 2),
    (ASKING_HOBBIES, "hobbies", "Kokie tavo pomėgiai?", lambda x: len(x.strip()) >= 2),
]

# Rate limiting cache
user_last_message = {}
user_states = {}

def get_question_text(field: str, language: str = "LT") -> str:
    """Get question text in the appropriate language."""
    questions = {
        "LT": {
            "language": "Kokia kalba nori gauti horoskopą? (LT/EN/RU/LV)",
            "name": "Koks tavo vardas?",
            "sex": "Kokia tavo lytis? (moteris/vyras)",
            "birthday": "Kokia tavo gimimo data? (pvz.: 1979-05-04)",
            "profession": "Kokia tavo profesija?",
            "hobbies": "Kokie tavo pomėgiai?"
        },
        "EN": {
            "language": "What language do you want to receive horoscopes in? (LT/EN/RU/LV)",
            "name": "What is your name?",
            "sex": "What is your gender? (woman/man)",
            "birthday": "What is your birth date? (e.g.: 1979-05-04)",
            "profession": "What is your profession?",
            "hobbies": "What are your hobbies?"
        },
        "RU": {
            "language": "На каком языке вы хотите получать гороскопы? (LT/EN/RU/LV)",
            "name": "Как вас зовут?",
            "sex": "Какой у вас пол? (женщина/мужчина)",
            "birthday": "Какая у вас дата рождения? (например: 1979-05-04)",
            "profession": "Какая у вас профессия?",
            "hobbies": "Какие у вас хобби?"
        },
        "LV": {
            "language": "Kādā valodā vēlaties saņemt horoskopus? (LT/EN/RU/LV)",
            "name": "Kāds ir jūsu vārds?",
            "sex": "Kāds ir jūsu dzimums? (sieviete/vīrietis)",
            "birthday": "Kāda ir jūsu dzimšanas datums? (piemēram: 1979-05-04)",
            "profession": "Kāda ir jūsu profesija?",
            "hobbies": "Kādi ir jūsu hobiji?"
        }
    }
    return questions.get(language, questions["LT"]).get(field, "")

def _validate_date(date_str: str) -> bool:
    """Validate date format."""
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False

def get_zodiac_sign(birthday: str) -> str:
    """Calculate zodiac sign from birthday (YYYY-MM-DD format)."""
    try:
        date_obj = datetime.strptime(birthday, '%Y-%m-%d')
        month = date_obj.month
        day = date_obj.day
        
        # Zodiac sign dates
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Avinas"  # Aries
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Jautis"  # Taurus
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Dvyniai"  # Gemini
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Vėžys"  # Cancer
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Liūtas"  # Leo
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Mergelė"  # Virgo
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Svarstyklės"  # Libra
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Skorpionas"  # Scorpio
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Šaulys"  # Sagittarius
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Ožiaragis"  # Capricorn
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Vandenis"  # Aquarius
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Žuvys"  # Pisces
    except ValueError:
        return "Nežinomas"  # Unknown

def get_zodiac_sign_en(birthday: str) -> str:
    """Calculate zodiac sign in English from birthday (YYYY-MM-DD format)."""
    try:
        date_obj = datetime.strptime(birthday, '%Y-%m-%d')
        month = date_obj.month
        day = date_obj.day
        
        # Zodiac sign dates
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Aries"
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Taurus"
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Gemini"
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Cancer"
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Leo"
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Virgo"
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Libra"
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Scorpio"
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Sagittarius"
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Capricorn"
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Aquarius"
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Pisces"
    except ValueError:
        return "Unknown"

def get_zodiac_sign_ru(birthday: str) -> str:
    """Calculate zodiac sign in Russian from birthday (YYYY-MM-DD format)."""
    try:
        date_obj = datetime.strptime(birthday, '%Y-%m-%d')
        month = date_obj.month
        day = date_obj.day
        
        # Zodiac sign dates
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Овен"
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Телец"
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Близнецы"
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Рак"
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Лев"
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Дева"
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Весы"
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Скорпион"
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Стрелец"
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Козерог"
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Водолей"
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Рыбы"
    except ValueError:
        return "Неизвестно"

def get_zodiac_sign_lv(birthday: str) -> str:
    """Calculate zodiac sign in Latvian from birthday (YYYY-MM-DD format)."""
    try:
        date_obj = datetime.strptime(birthday, '%Y-%m-%d')
        month = date_obj.month
        day = date_obj.day
        
        # Zodiac sign dates
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Auns"  # Aries
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Vērsis"  # Taurus
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Dvīņi"  # Gemini
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Vēzis"  # Cancer
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Lauva"  # Leo
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Jaunava"  # Virgo
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Svari"  # Libra
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Skorpions"  # Scorpio
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Strēlnieks"  # Sagittarius
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Mežāzis"  # Capricorn
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Ūdensvīrs"  # Aquarius
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Zivis"  # Pisces
    except ValueError:
        return "Nezināms"

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
            language TEXT NOT NULL CHECK (language IN ('LT', 'EN', 'RU', 'LV')),
            profession TEXT NOT NULL,
            hobbies TEXT NOT NULL,
            sex TEXT NOT NULL CHECK (sex IN ('moteris', 'vyras')),
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
    global user_last_message
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
    logger.info(f"Start command received from chat_id: {chat_id}")
    
    # Clear any existing conversation state
    context.user_data.clear()
    
    if is_rate_limited(chat_id):
        logger.warning(f"User {chat_id} is rate limited")
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
        logger.info(f"Existing user {existing_user[0]} found for chat_id: {chat_id}")
        await update.message.reply_text(
            f"Labas, {existing_user[0]}! 🌟\n\n"
            "Tu jau esi užsiregistravęs! Gali:\n"
            "• /horoscope - Gauti šiandienos horoskopą\n"
            "• /profile - Peržiūrėti savo profilį\n"
            "• /update - Atnaujinti duomenis\n"
            "• /help - Pagalba"
        )
        return ConversationHandler.END
    
    logger.info(f"Starting registration for new user chat_id: {chat_id}")
    try:
        await update.message.reply_text(
            "Labas! Aš esu tavo asmeninis horoskopų botukas 🌟\n\n"
            "Atsakyk į kelis klausimus, kad galėčiau pritaikyti horoskopą būtent tau.\n\n"
            "Pradėkime nuo kalbos pasirinkimo:"
        )
        await update.message.reply_text(get_question_text("language", "LT"))
        logger.info(f"Registration message sent to chat_id: {chat_id}, returning ASKING_LANGUAGE")
        return ASKING_LANGUAGE
    except Exception as e:
        logger.error(f"Error sending registration message to {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandyk dar kartą.")
        return ConversationHandler.END

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
            ASKING_LANGUAGE: "Pasirink vieną iš: LT, EN, RU arba LV:",
            ASKING_PROFESSION: "Profesija turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            ASKING_HOBBIES: "Pomėgiai turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            ASKING_SEX: "Pasirink: moteris arba vyras:",
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
        _, next_field, _, _ = QUESTIONS[next_index]
        
        # Get the user's selected language for subsequent questions
        user_language = context.user_data.get('language', 'LT')
        next_question_text = get_question_text(next_field, user_language)
        
        # Get appropriate "Great!" message based on language
        great_messages = {
            "LT": "Puiku! 🌟",
            "EN": "Great! 🌟", 
            "RU": "Отлично! 🌟",
            "LV": "Lieliski! 🌟"
        }
        great_msg = great_messages.get(user_language, "Puiku! 🌟")
        
        await update.message.reply_text(f"{great_msg}\n\n{next_question_text}")
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
    (chat_id, name, birthday, language, profession, hobbies, sex, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        chat_id,
        context.user_data['name'],
        context.user_data['birthday'],
        context.user_data['language'],
        context.user_data['profession'],
        context.user_data['hobbies'],
        context.user_data['sex']
    ))
    conn.commit()
    
    await update.message.reply_text(
        f"Puiku, {context.user_data['name']}! 🎉\n\n"
        "Tavo profilis sukurtas! Nuo šiol kiekvieną rytą 07:30 (Lietuvos laiku) gausi savo asmeninį horoskopą! 🌞\n\n"
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



async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the registration process."""
    await update.message.reply_text(
        "Registracija atšaukta. Jei nori pradėti iš naujo, naudok /start"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user data and allow re-registration."""
    chat_id = update.effective_chat.id
    logger.info(f"Reset command received from chat_id: {chat_id}")
    
    if is_rate_limited(chat_id):
        await update.message.reply_text(
            f"⏳ Palaukite {RATE_LIMIT_SECONDS} sekundės prieš siųsdami kitą žinutę."
        )
        return
    
    # Delete user from database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    conn.commit()
    
    # Clear any conversation state
    context.user_data.clear()
    
    # Clear rate limiting cache for this user
    if chat_id in user_last_message:
        del user_last_message[chat_id]
    if chat_id in user_states:
        del user_states[chat_id]
    
    logger.info(f"User {chat_id} data reset successfully")
    
    await update.message.reply_text(
        "🔄 Tavo duomenys ištrinti! ✅\n\n"
        "Dabar gali pradėti registraciją iš naujo su komanda /start"
    )

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
    
    chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active = user
    
    # Check if user already got horoscope today
    today = datetime.now().date()
    if last_horoscope_date and datetime.strptime(last_horoscope_date, "%Y-%m-%d").date() == today:
        await update.message.reply_text(
            f"Labas, {name}! 🌟\n\n"
            "Tu jau gavai šiandienos horoskopą! Rytą 07:30 (Lietuvos laiku) gausi naują. 🌞"
        )
        return
    
    # Generate horoscope
    await update.message.reply_text("Generuoju tavo asmeninį horoskopą... ✨")
    
    try:
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex)
        
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
                           hobbies: str, sex: str) -> str:
    """Generate personalized horoscope using OpenAI with caching."""
    # Calculate zodiac sign based on language
    if language == "LT":
        zodiac_sign = get_zodiac_sign(birthday)
    elif language == "EN":
        zodiac_sign = get_zodiac_sign_en(birthday)
    elif language == "RU":
        zodiac_sign = get_zodiac_sign_ru(birthday)
    else:  # LV
        zodiac_sign = get_zodiac_sign_lv(birthday)
    
    # Create optimized prompt based on language
    prompts = {
        "LT": f"""Tu esi patyręs astrologas ir psichologas, kuris rašo asmeniškus horoskopus. Šiandien rašai horoskopą {name} ({sex}), gimusiam {birthday}.

Apie {name}:
- Zodiac ženklas: {zodiac_sign}
- Dirba: {profession}
- Mėgsta: {hobbies}

Rašyk natūralų, šiltą horoskopą, kuris:
- Skamba kaip tikras astrologo patarimas, ne kaip AI generuotas tekstas
- Naudoja {name} asmeninę informaciją natūraliai, ne kaip sąrašą
- Įtraukia {zodiac_sign} ženklo charakteristikas ir energiją
- Pateikia konkrečius, praktiškus patarimus, susijusius su jų gyvenimu
- Yra motyvuojantis, bet ne per optimistiškas
- Turi šiek tiek mistikos ir magijos, bet išlieka praktiškas
- Skamba kaip kalbėtum su draugu, ne kaip skaitytum iš knygos
- 4-6 sakiniai, natūraliai sujungti

Pradėk nuo šiandienos energijos ir {zodiac_sign} ženklo įtakos, tada pereik prie asmeninio patarimo.""",
        
        "EN": f"""You are an experienced astrologer and psychologist writing a personal horoscope. Today you're writing for {name} ({sex}), born on {birthday}.

About {name}:
- Zodiac sign: {zodiac_sign}
- Works as: {profession}
- Enjoys: {hobbies}

Write a natural, warm horoscope that:
- Sounds like genuine astrological advice, not AI-generated text
- Uses {name}'s personal information naturally, not as a checklist
- Incorporates {zodiac_sign} sign characteristics and energy
- Provides specific, practical advice related to their life
- Is motivating but not overly optimistic
- Has a touch of mysticism and magic, but stays practical
- Sounds like you're talking to a friend, not reading from a book
- 4-6 sentences, naturally connected

Start with today's energy and {zodiac_sign} sign influence, then move to personal advice.""",
        
        "RU": f"""Ты опытный астролог и психолог, пишущий личные гороскопы. Сегодня ты пишешь гороскоп для {name} ({sex}), родившегося {birthday}.

О {name}:
- Знак зодиака: {zodiac_sign}
- Работает: {profession}
- Увлекается: {hobbies}

Напиши естественный, тёплый гороскоп, который:
- Звучит как настоящий астрологический совет, а не как ИИ-генерированный текст
- Использует личную информацию {name} естественно, а не как список
- Включает характеристики и энергию знака {zodiac_sign}
- Даёт конкретные, практические советы, связанные с их жизнью
- Мотивирует, но не слишком оптимистичен
- Имеет немного мистики и магии, но остаётся практичным
- Звучит как разговор с другом, а не как чтение из книги
- 4-6 предложений, естественно связанных

Начни с энергии дня и влияния знака {zodiac_sign}, затем перейди к личному совету.""",
        
        "LV": f"""Tu esi pieredzējis astrologs un psihologs, kurš raksta personīgus horoskopus. Šodien tu raksti horoskopu {name} ({sex}), dzimis {birthday}.

Par {name}:
- Zodiaka zīme: {zodiac_sign}
- Strādā: {profession}
- Mīl: {hobbies}

Raksti dabisku, siltu horoskopu, kas:
- Izklausās kā īsts astroloģisks padoms, ne kā AI ģenerēts teksts
- Izmanto {name} personīgo informāciju dabiski, ne kā sarakstu
- Iekļauj {zodiac_sign} zīmes īpašības un enerģiju
- Sniedz konkrētus, praktiskus padomus, kas saistīti ar viņu dzīvi
- Ir motivējošs, bet ne pārāk optimistisks
- Ir ar mazliet mistikas un maģijas, bet paliek praktisks
- Izklausās kā saruna ar draugu, ne kā lasīšana no grāmatas
- 4-6 teikumi, dabiski savienoti

Sāc ar šodienas enerģiju un {zodiac_sign} zīmes ietekmi, tad pārej uz personīgo padomu."""
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
    
    chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active = user
    
    profile_text = f"""
👤 **Tavo profilis:**

🌍 **Kalba:** {language}
🌟 **Vardas:** {name}
👤 **Lytis:** {sex}
📅 **Gimimo data:** {birthday}
💼 **Profesija:** {profession}
🎨 **Pomėgiai:** {hobbies}
📅 **Registracijos data:** {created_at}
"""
    
    if last_horoscope_date:
        profile_text += f"📊 **Paskutinis horoskopas:** {last_horoscope_date}"
    
    await update.message.reply_text(profile_text)

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple test command to verify bot is working."""
    chat_id = update.effective_chat.id
    logger.info(f"Test command received from chat_id: {chat_id}")
    await update.message.reply_text("✅ Bot is working! Test command received.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = """
🌟 **Horoskopų Botas - Pagalba**

**Komandos:**
• /start - Pradėti registraciją
• /reset - Ištrinti duomenis ir pradėti iš naujo
• /test - Testuoti ar botas veikia
• /horoscope - Gauti šiandienos horoskopą
• /profile - Peržiūrėti savo profilį
• /test_horoscope - Testuoti horoskopo generavimą
• /help - Ši pagalba

**Kaip veikia:**
1. Užsiregistruok su /start
2. Atsakyk į klausimus
3. Gauk asmeninį horoskopą kiekvieną rytą 07:30 (Lietuvos laiku)
4. Naudok /horoscope, kad gautum horoskopą bet kada

**Funkcijos:**
✨ Asmeniški horoskopai pagal tavo duomenis
🌍 Palaiko LT, EN, RU kalbas
📅 Automatinis siuntimas kiekvieną rytą
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
    
    chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active = user
    
    await update.message.reply_text("🧪 Testuoju horoskopo generavimą...")
    
    try:
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex)
        await update.message.reply_text(f"✅ **Testinis horoskopas:**\n\n{horoscope}")
    except Exception as e:
        logger.error(f"Test horoscope error for user {chat_id}: {e}")
        await update.message.reply_text(f"❌ Klaida: {str(e)}")

async def send_today_horoscopes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually send today's horoscopes to all users (admin command)."""
    chat_id = update.effective_chat.id
    
    # Simple admin check (you can modify this)
    if chat_id != 658488948:  # Replace with your chat ID
        await update.message.reply_text("❌ Ši komanda prieinama tik administratoriui.")
        return
    
    await update.message.reply_text("📤 Siunčiu šiandienos horoskopus visiems vartotojams...")
    
    try:
        await send_daily_horoscopes()
        await update.message.reply_text("✅ Horoskopai išsiųsti visiems vartotojams!")
    except Exception as e:
        logger.error(f"Error sending today's horoscopes: {e}")
        await update.message.reply_text(f"❌ Klaida siunčiant horoskopus: {str(e)}")

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
            chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active = user
            task = send_horoscope_to_user(bot, user)
            tasks.append(task)
        
        # Wait for batch to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Small delay between batches
        if i + batch_size < len(all_users):
            await asyncio.sleep(1)

async def send_horoscope_to_user(bot, user):
    """Send horoscope to a single user."""
    chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active = user
    
    try:
        # Generate horoscope
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex)
        
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
    
    # Schedule for 07:30 Lithuania time
    # Server is already in Lithuania timezone, so use 07:30 server time
    schedule.every().day.at("07:30").do(run_async_horoscopes)
    logger.info("Daily horoscopes scheduled for 07:30 Lithuania time")
    
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
            ASKING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_language)],
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASKING_SEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sex)],
            ASKING_BIRTHDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_birthday)],
            ASKING_PROFESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_profession)],
            ASKING_HOBBIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_hobbies)],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
    )

    # Add handlers - IMPORTANT: ConversationHandler must be added first
    app.add_handler(registration_handler)
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("horoscope", get_horoscope_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("test_horoscope", test_horoscope_command))
    app.add_handler(CommandHandler("send_today", send_today_horoscopes_command))
    app.add_handler(CommandHandler("help", help_command))

    # Start scheduler in a separate thread
    scheduler_thread = threading.Thread(target=schedule_horoscopes, daemon=True)
    scheduler_thread.start()

    # Start the bot
    logger.info("Optimized horoscope bot is starting...")
    logger.info(f"Bot token: {TELEGRAM_BOT_TOKEN[:10]}..." if TELEGRAM_BOT_TOKEN else "No bot token!")
    logger.info(f"OpenAI model: {OPENAI_MODEL}")
    
    try:
        logger.info("Starting bot polling...")
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