import logging
import asyncio
import sqlite3
import schedule
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

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
    MAX_TOKENS, TEMPERATURE, OPENAI_MODEL, OPENAI_MODEL_FALLBACK
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

# Conversation states
(ASKING_NAME, ASKING_BIRTHDAY, ASKING_LANGUAGE, ASKING_PROFESSION, 
 ASKING_HOBBIES, ASKING_SEX, ASKING_INTERESTS) = range(7)

# Questions sequence
QUESTIONS = [
    (ASKING_NAME, "name", "Koks tavo vardas?"),
    (ASKING_BIRTHDAY, "birthday", "Kokia tavo gimimo data? (pvz.: 1979-05-04)"),
    (ASKING_LANGUAGE, "language", "Kokia kalba nori gauti horoskopą? (LT/EN/RU)"),
    (ASKING_PROFESSION, "profession", "Kokia tavo profesija?"),
    (ASKING_HOBBIES, "hobbies", "Kokie tavo pomėgiai?"),
    (ASKING_SEX, "sex", "Kokia tavo lytis? (moteris/vyras)"),
    (ASKING_INTERESTS, "interests", "Kuo labiausiai domiesi? (pvz.: šeima, karjera, kelionės)")
]

def initialize_database():
    """Initialize SQLite database for user profiles."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        name TEXT,
        birthday TEXT,
        language TEXT,
        profession TEXT,
        hobbies TEXT,
        sex TEXT,
        interests TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_horoscope_date DATE
    )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def initialize_openai_client():
    """Initialize OpenAI client."""
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the horoscope bot registration process."""
    chat_id = update.effective_chat.id
    
    # Check if user already exists
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE chat_id = ?", (chat_id,))
    existing_user = cursor.fetchone()
    conn.close()
    
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

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's name."""
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Vardas turi būti bent 2 simbolių ilgio. Bandyk dar kartą:")
        return ASKING_NAME
    
    context.user_data['name'] = name
    await update.message.reply_text(
        f"Puiku, {name}! 🌟\n\n"
        "Dabar pasakyk savo gimimo datą (formatas: YYYY-MM-DD):"
    )
    return ASKING_BIRTHDAY

async def ask_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's birthday."""
    birthday = update.message.text.strip()
    
    try:
        # Validate date format
        datetime.strptime(birthday, "%Y-%m-%d")
        context.user_data['birthday'] = birthday
        await update.message.reply_text(
            "Puiku! 📅\n\n"
            "Kokia kalba nori gauti horoskopą?\n"
            "• LT - Lietuvių kalba\n"
            "• EN - English\n"
            "• RU - Русский"
        )
        return ASKING_LANGUAGE
    except ValueError:
        await update.message.reply_text(
            "Neteisingas datos formatas! Naudok formatą YYYY-MM-DD (pvz.: 1990-05-15):"
        )
        return ASKING_BIRTHDAY

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for preferred language."""
    language = update.message.text.strip().upper()
    
    if language not in ['LT', 'EN', 'RU']:
        await update.message.reply_text(
            "Pasirink vieną iš: LT, EN arba RU:"
        )
        return ASKING_LANGUAGE
    
    context.user_data['language'] = language
    await update.message.reply_text(
        "Puiku! 🌍\n\n"
        "Kokia tavo profesija?"
    )
    return ASKING_PROFESSION

async def ask_profession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's profession."""
    profession = update.message.text.strip()
    context.user_data['profession'] = profession
    await update.message.reply_text(
        "Puiku! 💼\n\n"
        "Kokie tavo pomėgiai?"
    )
    return ASKING_HOBBIES

async def ask_hobbies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's hobbies."""
    hobbies = update.message.text.strip()
    context.user_data['hobbies'] = hobbies
    await update.message.reply_text(
        "Puiku! 🎨\n\n"
        "Kokia tavo lytis?\n"
        "• moteris\n"
        "• vyras"
    )
    return ASKING_SEX

async def ask_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's sex."""
    sex = update.message.text.strip().lower()
    
    if sex not in ['moteris', 'vyras']:
        await update.message.reply_text(
            "Pasirink: moteris arba vyras:"
        )
        return ASKING_SEX
    
    context.user_data['sex'] = sex
    await update.message.reply_text(
        "Puiku! 👤\n\n"
        "Paskutinis klausimas: kuo labiausiai domiesi?\n"
        "(pvz.: šeima, karjera, kelionės, sveikata, meilė)"
    )
    return ASKING_INTERESTS

async def ask_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's interests and complete registration."""
    interests = update.message.text.strip()
    context.user_data['interests'] = interests
    
    # Save user data to database
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT OR REPLACE INTO users 
    (chat_id, name, birthday, language, profession, hobbies, sex, interests)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        context.user_data['name'],
        context.user_data['birthday'],
        context.user_data['language'],
        context.user_data['profession'],
        context.user_data['hobbies'],
        context.user_data['sex'],
        interests
    ))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"Puiku, {context.user_data['name']}! 🎉\n\n"
        "Tavo profilis sukurtas! Nuo šiol kiekvieną rytą 07:30 gausi savo asmeninį horoskopą! 🌞\n\n"
        "Gali naudoti:\n"
        "• /horoscope - Gauti šiandienos horoskopą\n"
        "• /profile - Peržiūrėti savo profilį\n"
        "• /update - Atnaujinti duomenis\n"
        "• /help - Pagalba"
    )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

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
    
    # Get user data
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date = user
    
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?",
            (today.strftime("%Y-%m-%d"), chat_id)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(horoscope)
        
    except Exception as e:
        logger.error(f"Error generating horoscope for user {chat_id}: {e}")
        await update.message.reply_text(
            "Atsiprašau, įvyko klaida generuojant horoskopą. Bandyk vėliau."
        )

async def generate_horoscope(name, birthday, language, profession, hobbies, sex, interests):
    """Generate personalized horoscope using OpenAI."""
    # Create language-specific prompt
    if language == "LT":
        prompt = f"""
Sukurk asmeninį dienos horoskopą {name} ({sex}), gimusiam {birthday}.

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

Sukurk horoskopą, kuris atitiktų šio žmogaus asmenybę ir gyvenimo situaciją.
"""
    elif language == "EN":
        prompt = f"""
Create a personalized daily horoscope for {name} ({sex}), born on {birthday}.

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

Create a horoscope that matches this person's personality and life situation.
"""
    else:  # RU
        prompt = f"""
Создай персональный дневной гороскоп для {name} ({sex}), родившегося {birthday}.

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

Создай гороскоп, который соответствует личности и жизненной ситуации этого человека.
"""
    
    # Make API call with fallback
    current_model = OPENAI_MODEL
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            if current_model == OPENAI_MODEL and OPENAI_MODEL_FALLBACK and attempt < MAX_RETRIES - 1:
                logger.warning(f"GPT-4 failed, falling back to {OPENAI_MODEL_FALLBACK}: {e}")
                current_model = OPENAI_MODEL_FALLBACK
                continue
            else:
                raise

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's profile."""
    chat_id = update.effective_chat.id
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date = user
    
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
    
    # Get user data
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text(
            "Tu dar neesi užsiregistravęs! Naudok /start, kad pradėtum."
        )
        return
    
    chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date = user
    
    await update.message.reply_text("🧪 Testuoju horoskopo generavimą...")
    
    try:
        horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex, interests)
        await update.message.reply_text(f"✅ **Testinis horoskopas:**\n\n{horoscope}")
    except Exception as e:
        logger.error(f"Test horoscope error for user {chat_id}: {e}")
        await update.message.reply_text(f"❌ Klaida: {str(e)}")

async def send_daily_horoscopes():
    """Send daily horoscopes to all registered users."""
    logger.info("Starting daily horoscope sending...")
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    all_users = cursor.fetchall()
    conn.close()
    
    if not all_users:
        logger.info("No users found for daily horoscopes")
        return
    
    logger.info(f"Found {len(all_users)} users for daily horoscopes")
    
    # Get the bot instance from the application
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    for user in all_users:
        chat_id, name, birthday, language, profession, hobbies, sex, interests, created_at, last_horoscope_date = user
        
        try:
            # Generate horoscope
            horoscope = await generate_horoscope(name, birthday, language, profession, hobbies, sex, interests)
            
            # Send horoscope
            await bot.send_message(chat_id=chat_id, text=horoscope)
            
            # Update last horoscope date
            today = datetime.now().date()
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_horoscope_date = ? WHERE chat_id = ?",
                (today.strftime("%Y-%m-%d"), chat_id)
            )
            conn.commit()
            conn.close()
            
            logger.info(f"Sent horoscope to {name} (chat_id: {chat_id})")
            
        except Exception as e:
            logger.error(f"Failed to send horoscope to {name} (chat_id: {chat_id}): {e}")

def schedule_horoscopes():
    """Schedule daily horoscope sending."""
    def run_async_horoscopes():
        import asyncio
        asyncio.run(send_daily_horoscopes())
    
    schedule.every().day.at("07:30").do(run_async_horoscopes)
    logger.info("Daily horoscopes scheduled for 07:30")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

async def main():
    """Start the horoscope bot."""
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
    logger.info("Horoscope bot is starting...")
    
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
