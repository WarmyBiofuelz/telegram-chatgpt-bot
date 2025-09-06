#!/usr/bin/env python3
"""
Registration Bot - Handles user registration and database management
This bot focuses solely on collecting user data and storing it in the database.
"""

import logging
import asyncio
import sqlite3
import os
import time
import schedule
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# Handle nest_asyncio for environments with existing event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler
from telegram import Update
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

# Database setup
DB_PATH = "horoscope_users.db"
_db_connection = None

# Global OpenAI client
client = None

# Conversation states (Language first, then Name, Sex, Birthday, Profession, Hobbies)
(ASKING_LANGUAGE, ASKING_NAME, ASKING_SEX, ASKING_BIRTHDAY, ASKING_PROFESSION, 
 ASKING_HOBBIES) = range(6)

# Questions sequence with validation
# Questions will be generated dynamically based on user's language

# Rate limiting cache
user_last_message = {}
user_states = {}

def _validate_date(date_str: str) -> bool:
    """Validate date format - accepts multiple formats."""
    date_str = date_str.strip()
    
    # Try different date formats
    formats = [
        "%Y-%m-%d",      # 1979-05-04
        "%d.%m.%Y",      # 04.05.1979
        "%d/%m/%Y",      # 04/05/1979
        "%m/%d/%Y",      # 05/04/1979
        "%d-%m-%Y",      # 04-05-1979
        "%Y.%m.%d",      # 1979.05.04
    ]
    
    for fmt in formats:
        try:
            datetime.strptime(date_str, fmt)
            return True
        except ValueError:
            continue
    
    return False

def _normalize_date(date_str: str) -> str:
    """Normalize date to YYYY-MM-DD format."""
    date_str = date_str.strip()
    
    # Try different date formats and convert to YYYY-MM-DD
    formats = [
        ("%Y-%m-%d", "%Y-%m-%d"),      # Already in correct format
        ("%d.%m.%Y", "%Y-%m-%d"),      # 04.05.1979 -> 1979-05-04
        ("%d/%m/%Y", "%Y-%m-%d"),      # 04/05/1979 -> 1979-05-04
        ("%m/%d/%Y", "%Y-%m-%d"),      # 05/04/1979 -> 1979-05-04
        ("%d-%m-%Y", "%Y-%m-%d"),      # 04-05-1979 -> 1979-05-04
        ("%Y.%m.%d", "%Y-%m-%d"),      # 1979.05.04 -> 1979-05-04
    ]
    
    for input_fmt, output_fmt in formats:
        try:
            date_obj = datetime.strptime(date_str, input_fmt)
            return date_obj.strftime(output_fmt)
        except ValueError:
            continue
    
    # If no format matches, return original (should not happen if validation passed)
    return date_str

def get_question_text(field: str, language: str = "LT") -> str:
    """Get question text in the appropriate language."""
    questions = {
        "LT": {
            "language": "🇱🇹 Rašyk LT lietuviškai\n🇬🇧 Type EN for English\n🇷🇺 Напиши RU по-русски\n🇱🇻 Raksti LV latviešu valodā",
            "name": "Koks tavo vardas?",
            "sex": "Kokia tavo lytis? (moteris/vyras)",
            "birthday": "Kokia tavo gimimo data? (pvz.: 1979-05-04, 04.05.1979, 04/05/1979)",
            "profession": "Kokia tavo profesija?",
            "hobbies": "Kokie tavo pomėgiai?"
        },
        "EN": {
            "language": "🇱🇹 Type LT for Lithuanian\n🇬🇧 Type EN for English\n🇷🇺 Type RU for Russian\n🇱🇻 Type LV for Latvian",
            "name": "What is your name?",
            "sex": "What is your gender? (woman/man/female/male)",
            "birthday": "What is your birth date? (e.g.: 1979-05-04, 04.05.1979, 04/05/1979)",
            "profession": "What is your profession?",
            "hobbies": "What are your hobbies?"
        },
        "RU": {
            "language": "🇱🇹 Напиши LT для литовского\n🇬🇧 Напиши EN для английского\n🇷🇺 Напиши RU для русского\n🇱🇻 Напиши LV для латышского",
            "name": "Как вас зовут?",
            "sex": "Какой у вас пол? (женщина/мужчина/женский/мужской)",
            "birthday": "Какая у вас дата рождения? (например: 1979-05-04, 04.05.1979, 04/05/1979)",
            "profession": "Какая у вас профессия?",
            "hobbies": "Какие у вас хобби?"
        },
        "LV": {
            "language": "🇱🇹 Raksti LT lietuviešu valodā\n🇬🇧 Raksti EN angļu valodā\n🇷🇺 Raksti RU krievu valodā\n🇱🇻 Raksti LV latviešu valodā",
            "name": "Kāds ir jūsu vārds?",
            "sex": "Kāds ir jūsu dzimums? (sieviete/vīrietis/virietis)",
            "birthday": "Kāda ir jūsu dzimšanas datums? (piemēram: 1979-05-04, 04.05.1979, 04/05/1979)",
            "profession": "Kāda ir jūsu profesija?",
            "hobbies": "Kādi ir jūsu hobiji?"
        }
    }
    return questions.get(language, questions["LT"]).get(field, "")

def get_message_text(message_type: str, language: str = "LT") -> str:
    """Get message text in the specified language."""
    messages = {
        "LT": {
            "welcome": "Labas! Aš esu tavo asmeninis horoskopų botukas 🌟",
            "continue": "Atsakyk į kelis klausimus, kad galėčiau pritaikyti horoskopą būtent tau.",
            "great": "Puiku!",
            "registration_complete": "Registracija baigta! Dabar gali gauti horoskopus.",
            "error_try_again": "Atsiprašau, įvyko klaida. Bandyk dar kartą.",
            "rate_limited": "Palaukite {seconds} sekundės prieš siųsdami kitą žinutę."
        },
        "EN": {
            "welcome": "Hello! I'm your personal horoscope bot 🌟",
            "continue": "Answer a few questions so I can personalize your horoscope.",
            "great": "Great!",
            "registration_complete": "Registration completed! Now you can receive horoscopes.",
            "error_try_again": "Sorry, an error occurred. Please try again.",
            "rate_limited": "Please wait {seconds} seconds before sending another message."
        },
        "RU": {
            "welcome": "Привет! Я твой личный бот-гороскоп 🌟",
            "continue": "Ответь на несколько вопросов, чтобы я мог составить персональный гороскоп для тебя.",
            "great": "Отлично!",
            "registration_complete": "Регистрация завершена! Теперь вы можете получать гороскопы.",
            "error_try_again": "Извините, произошла ошибка. Попробуйте еще раз.",
            "rate_limited": "Пожалуйста, подождите {seconds} секунд перед отправкой следующего сообщения."
        },
        "LV": {
            "welcome": "Sveiki! Esmu tavs personīgais horoskopu bots 🌟",
            "continue": "Atbildi uz dažiem jautājumiem, lai es varētu personalizēt tavu horoskopu.",
            "great": "Lieliski!",
            "registration_complete": "Reģistrācija pabeigta! Tagad varat saņemt horoskopus.",
            "error_try_again": "Atvainojiet, radās kļūda. Lūdzu, mēģiniet vēlreiz.",
            "rate_limited": "Lūdzu, gaidiet {seconds} sekundes pirms nosūtīt nākamo ziņojumu."
        }
    }
    return messages.get(language, messages["LT"]).get(message_type, "")

def get_error_message(field: str, language: str = "LT") -> str:
    """Get error message in the specified language."""
    error_messages = {
        "LT": {
            "name": "Vardas turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            "birthday": "Neteisingas datos formatas! Naudok formatą YYYY-MM-DD (pvz.: 1990-05-15):",
            "language": "Pasirink vieną iš: LT, EN, RU arba LV:",
            "profession": "Profesija turi būti bent 2 simbolių ilgio. Bandyk dar kartą:",
            "hobbies": "Pomėgiai turi būti 2-500 simbolių ilgio. Bandyk dar kartą:",
            "sex": "Pasirink: moteris arba vyras:",
        },
        "EN": {
            "name": "Name must be at least 2 characters long. Try again:",
            "birthday": "Invalid date format! Use YYYY-MM-DD format (e.g.: 1990-05-15):",
            "language": "Choose one of: LT, EN, RU or LV:",
            "profession": "Profession must be at least 2 characters long. Try again:",
            "hobbies": "Hobbies must be 2-500 characters long. Try again:",
            "sex": "Choose: woman or man:",
        },
        "RU": {
            "name": "Имя должно содержать не менее 2 символов. Попробуйте еще раз:",
            "birthday": "Неверный формат даты! Используйте формат YYYY-MM-DD (например: 1990-05-15):",
            "language": "Выберите один из: LT, EN, RU или LV:",
            "profession": "Профессия должна содержать не менее 2 символов. Попробуйте еще раз:",
            "hobbies": "Хобби должны содержать 2-500 символов. Попробуйте еще раз:",
            "sex": "Выберите: женщина или мужчина:",
        },
        "LV": {
            "name": "Vārdam jābūt vismaz 2 rakstzīmju garam. Mēģiniet vēlreiz:",
            "birthday": "Nepareizs datuma formāts! Izmantojiet formātu YYYY-MM-DD (piemēram: 1990-05-15):",
            "language": "Izvēlieties vienu no: LT, EN, RU vai LV:",
            "profession": "Profesijai jābūt vismaz 2 rakstzīmju garai. Mēģiniet vēlreiz:",
            "hobbies": "Hobijiem jābūt 2-500 rakstzīmju garam. Mēģiniet vēlreiz:",
            "sex": "Izvēlieties: sieviete vai vīrietis:",
        }
    }
    return error_messages.get(language, error_messages["LT"]).get(field, "")

def get_db_connection():
    """Get database connection with optimizations."""
    global _db_connection
    try:
        if _db_connection is None:
            _db_connection = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
            _db_connection.execute("PRAGMA journal_mode=WAL")
            _db_connection.execute("PRAGMA synchronous=NORMAL")
            _db_connection.execute("PRAGMA cache_size=10000")
            _db_connection.execute("PRAGMA temp_store=MEMORY")
            logger.info("Database connection established successfully")
        return _db_connection
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        # Try to create a new connection
        try:
            _db_connection = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
            _db_connection.execute("PRAGMA journal_mode=WAL")
            _db_connection.execute("PRAGMA synchronous=NORMAL")
            _db_connection.execute("PRAGMA cache_size=10000")
            _db_connection.execute("PRAGMA temp_store=MEMORY")
            logger.info("Database connection re-established successfully")
            return _db_connection
        except Exception as e2:
            logger.error(f"Failed to re-establish database connection: {e2}")
            raise

def initialize_database():
    """Initialize SQLite database for user profiles with optimizations."""
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        
        # Check if old schema exists and migrate
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'interests' in columns:
            logger.info("Migrating database schema - removing interests column")
            # Create new table without interests
            conn.execute("""
                CREATE TABLE users_new (
                    chat_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    birthday TEXT NOT NULL,
                    language TEXT NOT NULL CHECK (language IN ('LT', 'EN', 'RU', 'LV')),
                    profession TEXT,
                    hobbies TEXT,
                    sex TEXT NOT NULL CHECK (sex IN ('moteris', 'vyras', 'woman', 'man', 'female', 'male', 'женщина', 'мужчина', 'женский', 'мужской', 'sieviete', 'vīrietis', 'virietis', 'sieviešu', 'vīriešu')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_horoscope_date DATE,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Copy data from old table to new table
            conn.execute("""
                INSERT INTO users_new (chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active)
                SELECT chat_id, name, birthday, language, profession, hobbies, sex, created_at, last_horoscope_date, is_active
                FROM users
            """)
            
            # Drop old table and rename new table
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_new RENAME TO users")
            
            logger.info("Database schema migration completed")
        
        # Create users table with optimized schema (if it doesn't exist)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            birthday TEXT NOT NULL,
            language TEXT NOT NULL CHECK (language IN ('LT', 'EN', 'RU', 'LV')),
            profession TEXT,
            hobbies TEXT,
            sex TEXT NOT NULL CHECK (sex IN ('moteris', 'vyras', 'woman', 'man', 'женщина', 'мужчина', 'sieviete', 'vīrietis')),
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

def is_rate_limited(chat_id: int) -> bool:
    """Check if user is rate limited."""
    global user_last_message
    current_time = time.time()
    
    if chat_id in user_last_message:
        time_diff = current_time - user_last_message[chat_id]
        if time_diff < RATE_LIMIT_SECONDS:
            return True
    
    user_last_message[chat_id] = current_time
    return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the registration process."""
    chat_id = update.effective_chat.id
    logger.info(f"Start command received from chat_id: {chat_id}")
    
    # Clear any existing conversation state
    context.user_data.clear()
    
    if is_rate_limited(chat_id):
        logger.warning(f"User {chat_id} is rate limited")
        rate_limited_message = get_message_text("rate_limited", "LT").format(seconds=RATE_LIMIT_SECONDS)
        await update.message.reply_text(f"⏳ {rate_limited_message}")
        return ConversationHandler.END
    
    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
    existing_user = cursor.fetchone()
    conn.commit()
    
    if existing_user:
        logger.info(f"Existing user {existing_user[0]} found for chat_id: {chat_id}")
        # Get user's language for the message
        cursor.execute("SELECT language FROM users WHERE chat_id = ?", (chat_id,))
        user_language = cursor.fetchone()[0] if cursor.fetchone() else "LT"
        
        existing_user_messages = {
            "LT": f"Labas, {existing_user[0]}! 🌟\n\nTu jau esi užsiregistravęs! Gali:\n• /horoscope - Gauti šiandienos horoskopą\n• /profile - Peržiūrėti savo profilį\n• /update - Atnaujinti duomenis\n• /help - Pagalba",
            "EN": f"Hello, {existing_user[0]}! 🌟\n\nYou are already registered! You can:\n• /horoscope - Get today's horoscope\n• /profile - View your profile\n• /update - Update your data\n• /help - Help",
            "RU": f"Привет, {existing_user[0]}! 🌟\n\nВы уже зарегистрированы! Вы можете:\n• /horoscope - Получить сегодняшний гороскоп\n• /profile - Посмотреть профиль\n• /update - Обновить данные\n• /help - Помощь",
            "LV": f"Sveiki, {existing_user[0]}! 🌟\n\nJūs jau esat reģistrējies! Jūs varat:\n• /horoscope - Saņemt šodienas horoskopu\n• /profile - Apskatīt savu profilu\n• /update - Atjaunināt datus\n• /help - Palīdzība"
        }
        await update.message.reply_text(existing_user_messages.get(user_language, existing_user_messages["LT"]))
        return ConversationHandler.END
    
    logger.info(f"Starting registration for new user chat_id: {chat_id}")
    try:
        # Start with language selection (in Lithuanian as default)
        language_question_text = get_question_text("language", "LT")
        await update.message.reply_text(language_question_text)
        logger.info(f"Language selection message sent to chat_id: {chat_id}, returning ASKING_LANGUAGE")
        return ASKING_LANGUAGE
    except Exception as e:
        logger.error(f"Error sending registration message to {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandyk dar kartą.")
        return ConversationHandler.END

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_index: int):
    """Generic handler for all questions with validation."""
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    logger.info(f"Handling question {question_index} for {chat_id}: {user_input[:50]}...")
    
    if is_rate_limited(chat_id):
        logger.warning(f"User {chat_id} is rate limited")
        user_language = context.user_data.get('language', 'LT')
        rate_limited_message = get_message_text("rate_limited", user_language).format(seconds=RATE_LIMIT_SECONDS)
        await update.message.reply_text(f"⏳ {rate_limited_message}")
        return question_index
    
    try:
        # Define question mappings
        question_mappings = {
            ASKING_LANGUAGE: ("language", lambda x: x.strip().upper() in ['LT', 'EN', 'RU', 'LV']),
            ASKING_NAME: ("name", lambda x: len(x.strip()) >= 2),
            ASKING_SEX: ("sex", lambda x: x.strip().lower() in [
                # Lithuanian
                'moteris', 'vyras',
                # English
                'woman', 'man', 'female', 'male',
                # Russian
                'женщина', 'мужчина', 'женский', 'мужской',
                # Latvian
                'sieviete', 'vīrietis', 'virietis', 'sieviešu', 'vīriešu'
            ]),
            ASKING_BIRTHDAY: ("birthday", lambda x: _validate_date(x)),
            ASKING_PROFESSION: ("profession", lambda x: len(x.strip()) >= 2),
            ASKING_HOBBIES: ("hobbies", lambda x: len(x.strip()) >= 2 and len(x.strip()) <= 500),
        }
        field_name, validator = question_mappings[question_index]
        
        if not validator(user_input):
            logger.warning(f"Validation failed for {chat_id} on {field_name}: {user_input}")
            # Get user's selected language for error message
            user_language = context.user_data.get('language', 'LT')
            error_message = get_error_message(field_name, user_language)
            await update.message.reply_text(error_message)
            return question_index
    except Exception as e:
        logger.error(f"Error in handle_question for {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandyk dar kartą.")
        return question_index
    
    # Store the validated input with sanitization
    if field_name == "language":
        user_input = user_input.upper()
        # Store language and send welcome message in selected language
        context.user_data[field_name] = user_input
        logger.info(f"Stored {field_name} for {chat_id}: {user_input}")
        
        # Send welcome message in selected language
        welcome_message = get_message_text("welcome", user_input)
        continue_message = get_message_text("continue", user_input)
        await update.message.reply_text(f"{welcome_message}\n\n{continue_message}")
        
    elif field_name == "sex":
        user_input = user_input.lower()
        context.user_data[field_name] = user_input
        logger.info(f"Stored {field_name} for {chat_id}: {user_input}")
        
    elif field_name in ["name", "profession", "hobbies"]:
        # Sanitize text input - remove excessive whitespace and limit length
        user_input = " ".join(user_input.split())  # Remove extra whitespace
        if field_name == "hobbies":
            user_input = user_input[:500]  # Limit hobbies to 500 characters
        elif field_name == "name":
            user_input = user_input[:100]  # Limit name to 100 characters
        elif field_name == "profession":
            user_input = user_input[:200]  # Limit profession to 200 characters
        
        context.user_data[field_name] = user_input
        logger.info(f"Stored {field_name} for {chat_id}: {user_input[:50]}...")  # Log first 50 chars
    
    elif field_name == "birthday":
        # Normalize date to YYYY-MM-DD format
        normalized_date = _normalize_date(user_input)
        context.user_data[field_name] = normalized_date
        logger.info(f"Stored {field_name} for {chat_id}: {normalized_date}")
    
    else:
        # For other fields
        context.user_data[field_name] = user_input
        logger.info(f"Stored {field_name} for {chat_id}: {user_input}")
    
    # Move to next question or complete registration
    next_index = question_index + 1
    logger.info(f"Question {question_index} completed for {chat_id}, moving to question {next_index}")
    if next_index <= ASKING_HOBBIES:
        # Define question mappings for next question
        question_mappings = {
            ASKING_LANGUAGE: ("language", lambda x: x.strip().upper() in ['LT', 'EN', 'RU', 'LV']),
            ASKING_NAME: ("name", lambda x: len(x.strip()) >= 2),
            ASKING_SEX: ("sex", lambda x: x.strip().lower() in [
                # Lithuanian
                'moteris', 'vyras',
                # English
                'woman', 'man', 'female', 'male',
                # Russian
                'женщина', 'мужчина', 'женский', 'мужской',
                # Latvian
                'sieviete', 'vīrietis', 'virietis', 'sieviešu', 'vīriešu'
            ]),
            ASKING_BIRTHDAY: ("birthday", lambda x: _validate_date(x)),
            ASKING_PROFESSION: ("profession", lambda x: len(x.strip()) >= 2),
            ASKING_HOBBIES: ("hobbies", lambda x: len(x.strip()) >= 2 and len(x.strip()) <= 500),
        }
        next_field, _ = question_mappings[next_index]
        
        # Get the user's selected language for subsequent questions
        user_language = context.user_data.get('language', 'LT')
        
        # Get the next question text in the user's language
        next_question_text = get_question_text(next_field, user_language)
        
        # Get appropriate "Great!" message based on language
        great_msg = get_message_text("great", user_language) + " 🌟"
        
        await update.message.reply_text(f"{great_msg}\n\n{next_question_text}")
        return next_index
    else:
        # Complete registration
        logger.info(f"All questions completed for {chat_id}, starting registration completion")
        return await complete_registration(update, context)

async def complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete the registration process and save to database."""
    chat_id = update.effective_chat.id
    
    try:
        # Validate that all required fields are present
        required_fields = ['language', 'name', 'sex', 'birthday', 'profession', 'hobbies']
        for field in required_fields:
            if field not in context.user_data:
                logger.error(f"Missing required field {field} for {chat_id}")
                await update.message.reply_text("Atsiprašau, įvyko klaida registracijos metu. Naudok /reset ir pradėk iš naujo.")
                return ConversationHandler.END
        
        # Get user's language for completion message
        user_language = context.user_data.get('language', 'LT')
        
        # Save to database with character limits
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users 
            (chat_id, name, birthday, language, profession, hobbies, sex, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            context.user_data['name'][:100],  # Limit name to 100 characters
            context.user_data['birthday'],
            context.user_data['language'],
            context.user_data['profession'][:200],  # Limit profession to 200 characters
            context.user_data['hobbies'][:500],  # Limit hobbies to 500 characters
            context.user_data['sex'],
            1
        ))
        conn.commit()
        
        # Get appropriate completion message based on language
        completion_messages = {
            "LT": f"Puiku, {context.user_data['name']}! 🎉\n\nTavo profilis sukurtas! Nuo šiol kiekvieną rytą 07:30 (Lietuvos laiku) gausi savo asmeninį horoskopą! 🌞\n\nGali naudoti:\n• /horoscope - Gauti horoskopą bet kada\n• /profile - Peržiūrėti savo profilį\n• /help - Pagalba",
            "EN": f"Great, {context.user_data['name']}! 🎉\n\nYour profile has been created! From now on, every morning at 07:30 (Lithuanian time) you'll receive your personal horoscope! 🌞\n\nYou can use:\n• /horoscope - Get horoscope anytime\n• /profile - View your profile\n• /help - Help",
            "RU": f"Отлично, {context.user_data['name']}! 🎉\n\nВаш профиль создан! Отныне каждое утро в 07:30 (литовское время) вы будете получать свой личный гороскоп! 🌞\n\nВы можете использовать:\n• /horoscope - Получить гороскоп в любое время\n• /profile - Посмотреть профиль\n• /help - Помощь",
            "LV": f"Lieliski, {context.user_data['name']}! 🎉\n\nJūsu profils ir izveidots! No šī brīža katru rītu plkst. 07:30 (Lietuvas laiks) jūs saņemsiet savu personīgo horoskopu! 🌞\n\nJūs varat izmantot:\n• /horoscope - Saņemt horoskopu jebkurā laikā\n• /profile - Apskatīt savu profilu\n• /help - Palīdzība"
        }
        
        completion_message = completion_messages.get(user_language, completion_messages["LT"])
        await update.message.reply_text(completion_message)
        
        # Clear user data after successful registration
        context.user_data.clear()
        logger.info(f"Registration completed successfully for {chat_id}")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error completing registration for {chat_id}: {e}")
        logger.error(f"User data that caused error: {context.user_data}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {str(e)}")
        
        # Get appropriate error message based on language
        user_language = context.user_data.get('language', 'LT')
        error_message = get_message_text("error_try_again", user_language) + " Naudok /reset ir pradėk iš naujo."
        await update.message.reply_text(error_message)
        return ConversationHandler.END

# Question handlers
async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_NAME)

async def ask_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_SEX)

async def ask_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_BIRTHDAY)

async def ask_profession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_PROFESSION)

async def ask_hobbies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_HOBBIES)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_question(update, context, ASKING_LANGUAGE)

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the registration process."""
    chat_id = update.effective_chat.id
    logger.info(f"Registration cancelled by {chat_id}")
    
    # Clear user data
    context.user_data.clear()
    
    await update.message.reply_text("Registracija atšaukta. Naudok /start, jei nori pradėti iš naujo.")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = """
🌟 **Horoskopų Botas - Pagalba**

**Komandos:**
• /start - Pradėti registraciją
• /horoscope - Gauti asmeninį horoskopą
• /help - Ši pagalba
• /reset - Ištrinti duomenis ir pradėti iš naujo
• /test_db - Patikrinti duomenų bazės būklę

**Registracijos procesas:**
1. Pasirinkite kalbą (LT/EN/RU/LV)
2. Įveskite savo vardą
3. Pasirinkite lytį
4. Įveskite gimimo datą (YYYY-MM-DD)
5. Įveskite profesiją
6. Įveskite pomėgius

**Po registracijos:**
• Naudokite /horoscope komandą bet kada
• Gausite asmeninį horoskopą pagal jūsų duomenis
• Horoskopas bus pritaikytas jūsų zodiac ženklui
"""
    await update.message.reply_text(help_text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user data and allow re-registration."""
    chat_id = update.effective_chat.id
    logger.info(f"Reset command received from {chat_id}")
    
    try:
        # Delete user from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
        conn.commit()
        
        # Clear user data and caches
        context.user_data.clear()
        if chat_id in user_last_message:
            del user_last_message[chat_id]
        if chat_id in user_states:
            del user_states[chat_id]
        
        await update.message.reply_text("✅ Duomenys ištrinti! Naudok /start, kad pradėtum registraciją iš naujo.")
        logger.info(f"User data reset for {chat_id}")
        
    except Exception as e:
        logger.error(f"Error resetting user data for {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandyk dar kartą.")
    
    return ConversationHandler.END

async def test_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test database connection and basic functionality."""
    chat_id = update.effective_chat.id
    logger.info(f"Database test requested by {chat_id}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Test basic database operations
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        
        await update.message.reply_text(
            f"✅ Database test successful!\n"
            f"📊 Total users: {user_count}\n"
            f"📋 Table columns: {len(columns)}\n"
            f"🔗 Connection: Active"
        )
        logger.info(f"Database test completed successfully for {chat_id}")
        
    except Exception as e:
        logger.error(f"Database test failed for {chat_id}: {e}")
        await update.message.reply_text(f"❌ Database test failed: {e}")

def get_zodiac_sign(birthday_str: str, language: str = "LT") -> str:
    """Calculate zodiac sign based on birthday and language."""
    try:
        month, day = map(int, birthday_str.split('-')[1:3])
        
        # Zodiac signs with correct date ranges
        zodiac_signs = [
            # (start_month, start_day, end_month, end_day, LT, EN, RU, LV)
            (3, 21, 4, 19, "Avinas", "Aries", "Овен", "Auns"),           # Aries
            (4, 20, 5, 20, "Jautis", "Taurus", "Телец", "Vērsis"),      # Taurus
            (5, 21, 6, 20, "Dvyniai", "Gemini", "Близнецы", "Dvīņi"),   # Gemini
            (6, 21, 7, 22, "Vėžys", "Cancer", "Рак", "Vēzis"),          # Cancer
            (7, 23, 8, 22, "Liūtas", "Leo", "Лев", "Lauva"),            # Leo
            (8, 23, 9, 22, "Mergelė", "Virgo", "Дева", "Jaunava"),      # Virgo
            (9, 23, 10, 22, "Svarstyklės", "Libra", "Весы", "Svari"),   # Libra
            (10, 23, 11, 21, "Skorpionas", "Scorpio", "Скорпион", "Skorpions"), # Scorpio
            (11, 22, 12, 21, "Šaulys", "Sagittarius", "Стрелец", "Strēlnieks"), # Sagittarius
            (12, 22, 1, 19, "Ožiaragis", "Capricorn", "Козерог", "Mežāzis"),    # Capricorn
            (1, 20, 2, 18, "Vandenis", "Aquarius", "Водолей", "Ūdensvīrs"),     # Aquarius
            (2, 19, 3, 20, "Žuvys", "Pisces", "Рыбы", "Zivis")          # Pisces
        ]
        
        for start_month, start_day, end_month, end_day, lt, en, ru, lv in zodiac_signs:
            # Handle year boundary (Capricorn: Dec 22 - Jan 19)
            if start_month > end_month:  # Crosses year boundary
                if (month == start_month and day >= start_day) or (month == end_month and day <= end_day):
                    languages = {"LT": lt, "EN": en, "RU": ru, "LV": lv}
                    return languages.get(language, lt)
            else:  # Normal case
                if (month == start_month and day >= start_day) or (month == end_month and day <= end_day):
                    languages = {"LT": lt, "EN": en, "RU": ru, "LV": lv}
                    return languages.get(language, lt)
        
        # Fallback
        return "Mergelė" if language == "LT" else "Virgo"
    except:
        return "Mergelė" if language == "LT" else "Virgo"

async def generate_horoscope(chat_id: int, user_data: dict) -> str:
    """Generate personalized horoscope using OpenAI."""
    global client
    
    try:
        if client is None:
            client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT)
        
        # Get zodiac sign
        zodiac = get_zodiac_sign(user_data['birthday'], user_data['language'])
        
        # Create personalized prompt
        prompts = {
            "LT": f"""Sukurk asmeninį horoskopą šiandienai žmogui:
Vardas: {user_data['name']}
Lytis: {user_data['sex']}
Gimimo data: {user_data['birthday']}
Zodiac ženklas: {zodiac}
Profesija: {user_data['profession']}
Pomėgiai: {user_data['hobbies']}

Horoskopas turi būti:
- Asmeniškas ir pritaikytas šiam žmogui
- 4-5 sakiniai
- Teigiamas ir motyvuojantis
- Pateikti praktinius patarimus
- Įtraukti humorą ir optimizmą
- Paminėti zodiac ženklą natūraliai

Atsakyk tik horoskopo tekstu, be papildomų komentarų.""",
            
            "EN": f"""Create a personalized horoscope for today for a person:
Name: {user_data['name']}
Gender: {user_data['sex']}
Birth date: {user_data['birthday']}
Zodiac sign: {zodiac}
Profession: {user_data['profession']}
Hobbies: {user_data['hobbies']}

The horoscope should be:
- Personal and tailored to this person
- 4-5 sentences
- Positive and motivating
- Provide practical advice
- Include humor and optimism
- Mention zodiac sign naturally

Respond only with the horoscope text, no additional comments.""",
            
            "RU": f"""Создай персональный гороскоп на сегодня для человека:
Имя: {user_data['name']}
Пол: {user_data['sex']}
Дата рождения: {user_data['birthday']}
Знак зодиака: {zodiac}
Профессия: {user_data['profession']}
Хобби: {user_data['hobbies']}

Гороскоп должен быть:
- Личным и адаптированным к этому человеку
- 4-5 предложений
- Позитивным и мотивирующим
- Давать практические советы
- Включать юмор и оптимизм
- Упоминать знак зодиака естественно

Отвечай только текстом гороскопа, без дополнительных комментариев.""",
            
            "LV": f"""Izveido personīgu horoskopu šodienai cilvēkam:
Vārds: {user_data['name']}
Dzimums: {user_data['sex']}
Dzimšanas datums: {user_data['birthday']}
Zodiac zīme: {zodiac}
Profesija: {user_data['profession']}
Hobiji: {user_data['hobbies']}

Horoskopam jābūt:
- Personīgam un pielāgotam šim cilvēkam
- 4-5 teikumiem
- Pozitīvam un motivējošam
- Sniegt praktiskus padomus
- Iekļaut humoru un optimismu
- Dabiski pieminēt zodiac zīmi

Atbildi tikai ar horoskopa tekstu, bez papildu komentāriem."""
        }
        
        prompt = prompts.get(user_data['language'], prompts["LT"])
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error generating horoscope for {chat_id}: {e}")
        error_messages = {
            "LT": "Atsiprašau, nepavyko sugeneruoti horoskopo. Bandykite vėliau.",
            "EN": "Sorry, couldn't generate horoscope. Please try again later.",
            "RU": "Извините, не удалось сгенерировать гороскоп. Попробуйте позже.",
            "LV": "Atvainojiet, neizdevās ģenerēt horoskopu. Mēģiniet vēlāk."
        }
        return error_messages.get(user_data.get('language', 'LT'), error_messages["LT"])

async def horoscope_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /horoscope command."""
    chat_id = update.effective_chat.id
    logger.info(f"Horoscope command received from {chat_id}")
    
    try:
        # Get user data from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
        user_row = cursor.fetchone()
        
        if not user_row:
            # User not registered
            not_registered_messages = {
                "LT": "Jūs dar neesate užsiregistravę! Naudokite /start komandą registracijai.",
                "EN": "You are not registered yet! Use /start command to register.",
                "RU": "Вы еще не зарегистрированы! Используйте команду /start для регистрации.",
                "LV": "Jūs vēl neesat reģistrējies! Izmantojiet /start komandu reģistrācijai."
            }
            await update.message.reply_text(not_registered_messages.get("LT", not_registered_messages["LT"]))
            return
        
        # Convert row to dict
        user_data = {
            'name': user_row[1],
            'birthday': user_row[2],
            'language': user_row[3],
            'profession': user_row[4],
            'hobbies': user_row[5],
            'sex': user_row[6]
        }
        
        # Generate horoscope
        loading_messages = {
            "LT": "🔮 Generuoju jūsų asmeninį horoskopą...",
            "EN": "🔮 Generating your personal horoscope...",
            "RU": "🔮 Генерирую ваш личный гороскоп...",
            "LV": "🔮 Ģenerēju jūsu personīgo horoskopu..."
        }
        
        loading_msg = await update.message.reply_text(
            loading_messages.get(user_data['language'], loading_messages["LT"])
        )
        
        horoscope = await generate_horoscope(chat_id, user_data)
        
        # Delete loading message and send horoscope
        await loading_msg.delete()
        await update.message.reply_text(f"🌟 **{user_data['name']}**, jūsų horoskopas šiandienai:\n\n{horoscope}")
        
        # Update last horoscope date
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?", (today, chat_id))
        conn.commit()
        
        logger.info(f"Horoscope sent successfully to {chat_id}")
        
    except Exception as e:
        logger.error(f"Error in horoscope command for {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandykite dar kartą.")

async def send_daily_horoscopes():
    """Send daily horoscopes to all registered users at 7:30 AM Lithuanian time."""
    lithuania_tz = timezone(timedelta(hours=3))  # Lithuania is UTC+3
    logger.info("Starting daily horoscope sending...")
    
    try:
        # Get all active users who haven't received today's horoscope
        conn = get_db_connection()
        cursor = conn.cursor()
        today = datetime.now(lithuania_tz).strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT chat_id, name, birthday, language, profession, hobbies, sex 
            FROM users 
            WHERE is_active = 1 AND (last_horoscope_date IS NULL OR last_horoscope_date != ?)
        """, (today,))
        
        users = cursor.fetchall()
        logger.info(f"Found {len(users)} users to send horoscopes to")
        
        if not users:
            logger.info("No users need horoscopes today")
            return
        
        # Get bot instance for sending messages
        from telegram import Bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        sent_count = 0
        error_count = 0
        
        for user_row in users:
            try:
                chat_id = user_row[0]
                user_data = {
                    'name': user_row[1],
                    'birthday': user_row[2],
                    'language': user_row[3],
                    'profession': user_row[4],
                    'hobbies': user_row[5],
                    'sex': user_row[6]
                }
                
                # Generate horoscope
                horoscope = await generate_horoscope(chat_id, user_data)
                
                # Send horoscope
                morning_messages = {
                    "LT": f"🌅 Labas rytas, {user_data['name']}! Štai jūsų horoskopas šiandienai:",
                    "EN": f"🌅 Good morning, {user_data['name']}! Here's your horoscope for today:",
                    "RU": f"🌅 Доброе утро, {user_data['name']}! Вот ваш гороскоп на сегодня:",
                    "LV": f"🌅 Labrīt, {user_data['name']}! Šeit ir jūsu horoskopu šodienai:"
                }
                
                morning_msg = morning_messages.get(user_data['language'], morning_messages["LT"])
                full_message = f"{morning_msg}\n\n🌟 {horoscope}"
                
                await bot.send_message(chat_id=chat_id, text=full_message)
                
                # Update last horoscope date
                cursor.execute("UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?", (today, chat_id))
                conn.commit()
                
                sent_count += 1
                logger.info(f"Daily horoscope sent to {user_data['name']} ({chat_id})")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error sending daily horoscope to {chat_id}: {e}")
        
        logger.info(f"Daily horoscope sending completed: {sent_count} sent, {error_count} errors")
        
    except Exception as e:
        logger.error(f"Error in daily horoscope sending: {e}")

async def schedule_daily_horoscopes():
    """Schedule daily horoscope sending at 7:30 AM Lithuanian time."""
    lithuania_tz = timezone(timedelta(hours=3))  # Lithuania is UTC+3
    
    while True:
        try:
            now = datetime.now(lithuania_tz)
            target_time = now.replace(hour=7, minute=30, second=0, microsecond=0)
            
            # If target time has passed today, set for tomorrow
            if now >= target_time:
                target_time += timedelta(days=1)
            
            # Calculate wait time
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Next daily horoscope scheduled for: {target_time} (in {wait_seconds/3600:.2f} hours)")
            
            # Wait until target time
            await asyncio.sleep(wait_seconds)
            
            # Send daily horoscopes
            await send_daily_horoscopes()
            
        except Exception as e:
            logger.error(f"Error in horoscope scheduler: {e}")
            # Wait 1 hour before retrying
            await asyncio.sleep(3600)

async def main():
    """Main function to run the registration bot."""
    logger.info("Starting Registration Bot...")
    
    # Check for existing instance lock
    lock_file = Path("bot_instance.lock")
    if lock_file.exists():
        logger.warning("Another bot instance is already running. Exiting...")
        return
    
    # Create lock file
    lock_file.write_text(f"Bot started at {datetime.now()}")
    logger.info("Created instance lock file")
    
    try:
        # Initialize database
        initialize_database()
        
        # Create application
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
        
        # Add handlers
        app.add_handler(registration_handler)
        app.add_handler(CommandHandler("reset", reset_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("test_db", test_db_command))
        app.add_handler(CommandHandler("horoscope", horoscope_command))
        
        # Force polling mode for Render Hobby Plan compatibility
        logger.info("Starting bot in polling mode (Hobby Plan compatible)...")
        logger.info("Note: Webhooks may not work reliably on Render Hobby Plan")
        
        # Clear any existing webhook to prevent conflicts
        try:
            await app.bot.delete_webhook()
            logger.info("Cleared existing webhook")
        except Exception as e:
            logger.warning(f"Could not clear webhook: {e}")
        
        # Wait a bit to ensure webhook is cleared
        logger.info("Waiting 5 seconds to ensure webhook is cleared...")
        await asyncio.sleep(5)
        
        # Start daily horoscope scheduler in background
        logger.info("Starting daily horoscope scheduler...")
        scheduler_task = asyncio.create_task(schedule_daily_horoscopes())
        
        # Use polling mode
        logger.info("Starting polling mode...")
        await app.run_polling()
        
    finally:
        # Clean up lock file
        if lock_file.exists():
            lock_file.unlink()
            logger.info("Removed instance lock file")
        
        # Cancel scheduler task
        if 'scheduler_task' in locals():
            scheduler_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
