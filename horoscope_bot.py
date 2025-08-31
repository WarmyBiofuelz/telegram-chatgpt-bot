#!/usr/bin/env python3
"""
Horoscope Bot - Generates and sends horoscopes from database data
This bot focuses solely on generating horoscopes and sending them to users.
"""

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

# Global OpenAI client
client = None

# Database setup
DB_PATH = "horoscope_users.db"
_db_connection = None

# Rate limiting cache
user_last_message = {}

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

def initialize_openai_client():
    """Initialize OpenAI client with optimizations."""
    global client
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=OPENAI_TIMEOUT,
            max_retries=MAX_RETRIES
        )
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        raise

def get_zodiac_sign(birthday: str) -> str:
    """Get zodiac sign in Lithuanian based on birthday (YYYY-MM-DD format)."""
    try:
        month, day = map(int, birthday.split('-')[1:])
        
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Avinas"
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Jautis"
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Dvyniai"
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Vėžys"
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Liūtas"
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Mergelė"
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Svarstyklės"
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Skorpionas"
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Šaulys"
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Ožiaragis"
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Vandenis"
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Žuvys"
    except ValueError:
        return "Nežinomas"

def get_zodiac_sign_en(birthday: str) -> str:
    """Get zodiac sign in English based on birthday (YYYY-MM-DD format)."""
    try:
        month, day = map(int, birthday.split('-')[1:])
        
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
    """Get zodiac sign in Russian based on birthday (YYYY-MM-DD format)."""
    try:
        month, day = map(int, birthday.split('-')[1:])
        
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
    """Get zodiac sign in Latvian based on birthday (YYYY-MM-DD format)."""
    try:
        month, day = map(int, birthday.split('-')[1:])
        
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Auns"
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Vērsis"
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Dvīņi"
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Vēzis"
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Lauva"
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Jaunava"
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Svari"
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Skorpions"
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Strēlnieks"
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Mežāzis"
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Ūdensvīrs"
        else:  # (month == 2 and day >= 19) or (month == 3 and day <= 20)
            return "Zivis"
    except ValueError:
        return "Nezināms"

async def generate_horoscope(name: str, birthday: str, language: str, profession: str, hobbies: str, sex: str) -> str:
    """Generate personalized horoscope using OpenAI."""
    try:
        # Get zodiac sign based on language
        if language == "LT":
            zodiac_sign = get_zodiac_sign(birthday)
        elif language == "EN":
            zodiac_sign = get_zodiac_sign_en(birthday)
        elif language == "RU":
            zodiac_sign = get_zodiac_sign_ru(birthday)
        elif language == "LV":
            zodiac_sign = get_zodiac_sign_lv(birthday)
        else:
            zodiac_sign = get_zodiac_sign(birthday)  # Default to Lithuanian
        
        # Create prompts based on language
        prompts = {
            "LT": f"""Tu esi patyręs astrologas ir psichologas, kuris kuria asmeninius horoskopus. Sukurk natūralų, autentišką horoskopą šiandienai.

Apie {name}:
- Vardas: {name}
- Gimimo data: {birthday}
- Zodiac ženklas: {zodiac_sign}
- Lytis: {sex}
- Profesija: {profession}
- Pomėgiai: {hobbies}

Instrukcijos:
- Sukurk 4-6 sakinius, natūraliai sujungtus
- Pradėk nuo šiandienos energijos
- Įtraukia {zodiac_sign} ženklo charakteristikas ir energiją
- Pateik praktinius patarimus
- Būk optimistiškas, bet realistiškas
- Naudok natūralų, šiltą toną
- Išvengk banalumo ir bendrų frazių
- Pritaikyk prie {name} asmenybės ir gyvenimo situacijos

Horoskopas:""",
            
            "EN": f"""You are an experienced astrologer and psychologist who creates personal horoscopes. Create a natural, authentic horoscope for today.

About {name}:
- Name: {name}
- Birth date: {birthday}
- Zodiac sign: {zodiac_sign}
- Gender: {sex}
- Profession: {profession}
- Hobbies: {hobbies}

Instructions:
- Create 4-6 sentences, naturally connected
- Start with today's energy
- Include {zodiac_sign} sign characteristics and energy
- Provide practical advice
- Be optimistic but realistic
- Use natural, warm tone
- Avoid banality and generic phrases
- Adapt to {name}'s personality and life situation

Horoscope:""",
            
            "RU": f"""Ты опытный астролог и психолог, который создает личные гороскопы. Создай естественный, аутентичный гороскоп на сегодня.

О {name}:
- Имя: {name}
- Дата рождения: {birthday}
- Знак зодиака: {zodiac_sign}
- Пол: {sex}
- Профессия: {profession}
- Хобби: {hobbies}

Инструкции:
- Создай 4-6 предложений, естественно связанных
- Начни с энергии сегодняшнего дня
- Включи характеристики и энергию знака {zodiac_sign}
- Дай практические советы
- Будь оптимистичным, но реалистичным
- Используй естественный, теплый тон
- Избегай банальности и общих фраз
- Адаптируй к личности и жизненной ситуации {name}

Гороскоп:""",
            
            "LV": f"""Tu esi pieredzējis astrologs un psihologs, kurš izveido personīgus horoskopus. Izveido dabisku, autentisku horoskopu šodienai.

Par {name}:
- Vārds: {name}
- Dzimšanas datums: {birthday}
- Zodiaka zīme: {zodiac_sign}
- Dzimums: {sex}
- Profesija: {profession}
- Hobiji: {hobbies}

Instrukcijas:
- Izveido 4-6 teikumus, dabiskā veidā savienotus
- Sāc ar šodienas enerģiju
- Iekļauj {zodiac_sign} zīmes īpašības un enerģiju
- Sniedz praktiskus padomus
- Esi optimistisks, bet reālistisks
- Izmanto dabisku, siltu toni
- Izvairies no banalitātes un vispārīgām frāzēm
- Pielāgo {name} personībai un dzīves situācijai

Horoskops:"""
        }
        
        prompt = prompts.get(language, prompts["LT"])
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional astrologer and psychologist who creates personalized, authentic horoscopes."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            timeout=OPENAI_TIMEOUT
        )
        
        horoscope = response.choices[0].message.content.strip()
        logger.info(f"Generated horoscope for {name} ({language})")
        return horoscope
        
    except RateLimitError:
        logger.warning("OpenAI rate limit exceeded")
        return "Atsiprašau, šiuo metu negaliu sugeneruoti horoskopo. Bandykite vėliau."
    except APIError as e:
        logger.error(f"OpenAI API error: {e}")
        return "Atsiprašau, įvyko klaida generuojant horoskopą. Bandykite vėliau."
    except Exception as e:
        logger.error(f"Error generating horoscope: {e}")
        return "Atsiprašau, įvyko klaida. Bandykite vėliau."

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

async def get_horoscope_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get horoscope for the user."""
    chat_id = update.effective_chat.id
    
    if is_rate_limited(chat_id):
        await update.message.reply_text(
            f"⏳ Palaukite {RATE_LIMIT_SECONDS} sekundės prieš siųsdami kitą žinutę."
        )
        return
    
    try:
        # Get user data from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, birthday, language, profession, hobbies, sex FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
        user = cursor.fetchone()
        
        if not user:
            await update.message.reply_text(
                "Jūs dar nesate užsiregistravę! Naudokite /start komandą, kad pradėtumėte registraciją."
            )
            return
        
        name, birthday, language, profession, hobbies, sex = user
        
        # Generate horoscope
        await update.message.reply_text("🔮 Generuoju jūsų asmeninį horoskopą...")
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex)
        
        # Send horoscope
        await update.message.reply_text(f"🌟 **{name} horoskopas šiandienai:**\n\n{horoscope}")
        
        logger.info(f"Horoscope sent to {chat_id} ({name})")
        
    except Exception as e:
        logger.error(f"Error getting horoscope for {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandykite vėliau.")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile."""
    chat_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, birthday, language, profession, hobbies, sex, created_at FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,))
        user = cursor.fetchone()
        
        if not user:
            await update.message.reply_text(
                "Jūs dar nesate užsiregistravę! Naudokite /start komandą, kad pradėtumėte registraciją."
            )
            return
        
        name, birthday, language, profession, hobbies, sex, created_at = user
        
        # Get zodiac sign
        if language == "LT":
            zodiac_sign = get_zodiac_sign(birthday)
        elif language == "EN":
            zodiac_sign = get_zodiac_sign_en(birthday)
        elif language == "RU":
            zodiac_sign = get_zodiac_sign_ru(birthday)
        elif language == "LV":
            zodiac_sign = get_zodiac_sign_lv(birthday)
        else:
            zodiac_sign = get_zodiac_sign(birthday)
        
        profile_text = f"""
🌟 **Jūsų profilis:**

👤 **Vardas:** {name}
📅 **Gimimo data:** {birthday}
♈ **Zodiac ženklas:** {zodiac_sign}
🌍 **Kalba:** {language}
👔 **Profesija:** {profession}
🎯 **Pomėgiai:** {hobbies}
⚧ **Lytis:** {sex}
📝 **Registracijos data:** {created_at}
"""
        
        await update.message.reply_text(profile_text)
        
    except Exception as e:
        logger.error(f"Error showing profile for {chat_id}: {e}")
        await update.message.reply_text("Atsiprašau, įvyko klaida. Bandykite vėliau.")

async def send_horoscope_to_user(chat_id: int, name: str, birthday: str, language: str, profession: str, hobbies: str, sex: str):
    """Send horoscope to a specific user."""
    try:
        # Create bot instance for sending
        from telegram import Bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Generate horoscope
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex)
        
        # Send horoscope
        await bot.send_message(
            chat_id=chat_id,
            text=f"🌟 **{name} horoskopas šiandienai:**\n\n{horoscope}"
        )
        
        # Update last horoscope date
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?",
            (datetime.now().strftime("%Y-%m-%d"), chat_id)
        )
        conn.commit()
        
        logger.info(f"Daily horoscope sent to {chat_id} ({name})")
        
    except Exception as e:
        logger.error(f"Error sending horoscope to {chat_id}: {e}")

async def send_daily_horoscopes():
    """Send daily horoscopes to all active users."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chat_id, name, birthday, language, profession, hobbies, sex 
            FROM users 
            WHERE is_active = 1 
            AND (last_horoscope_date IS NULL OR last_horoscope_date < ?)
        """, (datetime.now().strftime("%Y-%m-%d"),))
        
        users = cursor.fetchall()
        logger.info(f"Found {len(users)} users to send horoscopes to")
        
        for user in users:
            chat_id, name, birthday, language, profession, hobbies, sex = user
            await send_horoscope_to_user(chat_id, name, birthday, language, profession, hobbies, sex)
            # Small delay between messages to avoid rate limiting
            await asyncio.sleep(1)
        
        logger.info("Daily horoscopes sent successfully")
        
    except Exception as e:
        logger.error(f"Error sending daily horoscopes: {e}")

def run_scheduler():
    """Run the scheduler in a separate thread."""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def schedule_horoscopes():
    """Schedule daily horoscope delivery."""
    schedule.every().day.at("07:30").do(
        lambda: asyncio.run(send_daily_horoscopes())
    )
    logger.info("Horoscope scheduler set for 07:30 daily")

async def send_today_horoscopes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to send horoscopes manually."""
    chat_id = update.effective_chat.id
    
    # Simple admin check (you can improve this)
    if chat_id not in [123456789]:  # Replace with your admin chat_id
        await update.message.reply_text("Atsiprašau, ši komanda prieinama tik administratoriams.")
        return
    
    await update.message.reply_text("📤 Siunčiu šiandienos horoskopus...")
    await send_daily_horoscopes()
    await update.message.reply_text("✅ Horoskopai išsiųsti!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = """
🌟 **Horoskopų Botas - Pagalba**

**Komandos:**
• /horoscope - Gauti šiandienos horoskopą
• /profile - Peržiūrėti savo profilį
• /help - Ši pagalba

**Automatinis pristatymas:**
• Kiekvieną rytą 07:30 (Lietuvos laiku) gausite asmeninį horoskopą

**Pastaba:**
Jei dar nesate užsiregistravę, naudokite registracijos botą.
"""
    await update.message.reply_text(help_text)

async def main():
    """Main function to run the horoscope bot."""
    logger.info("Starting Horoscope Bot...")
    
    # Initialize OpenAI client
    initialize_openai_client()
    
    # Schedule daily horoscopes
    schedule_horoscopes()
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Create application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("horoscope", get_horoscope_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("send_today", send_today_horoscopes_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Start the bot
    logger.info("Horoscope Bot started successfully!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
