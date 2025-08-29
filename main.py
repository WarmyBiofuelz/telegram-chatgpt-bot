import logging
import asyncio
import time
import os
import tempfile
import re
from collections import defaultdict
from datetime import datetime, timedelta

# Handle nest_asyncio for environments with existing event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from shared.config import (
    TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LOG_FORMAT, LOG_LEVEL,
    RATE_LIMIT_SECONDS, MAX_RETRIES, RETRY_DELAY, OPENAI_TIMEOUT,
    MAX_TOKENS, TEMPERATURE, OPENAI_MODEL, OPENAI_MODEL_FALLBACK
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

# Lithuanian language detection patterns
LITHUANIAN_PATTERNS = [
    r'\b(ir|ar|bet|tačiau|todėl|nes|kadangi|jei|kai|kol|kad|kur|kaip|kodėl|koks|kokia|kuris|kurie)\b',
    r'\b(mano|tavo|jo|jos|mūsų|jūsų|savo|šio|šios|šio|šios|to|tos|to|tos)\b',
    r'\b(aš|tu|jis|ji|mes|jus|jie|jos|tai|šis|šie|šios|tas|tie|tos)\b',
    r'\b(esu|esi|yra|esame|esate|yra|buvo|bus|būsiu|būsi|būs|būsime|būsite|būs)\b',
    r'\b(gerai|blogai|gražiai|greitai|lėtai|aukštai|žemai|daug|mažai|nemažai|visai|visiškai)\b',
    r'\b(taip|ne|galbūt|tikrai|žinoma|žinoma|aišku|aišku|suprantama|suprantama)\b'
]

def detect_language(text):
    """Detect if text is in Lithuanian or another language."""
    if not text:
        return "unknown"
    
    text_lower = text.lower()
    
    # Count Lithuanian-specific words and patterns
    lithuanian_score = 0
    for pattern in LITHUANIAN_PATTERNS:
        matches = re.findall(pattern, text_lower)
        lithuanian_score += len(matches)
    
    # Check for Lithuanian-specific characters
    lithuanian_chars = len(re.findall(r'[ąčęėįšųūž]', text_lower))
    lithuanian_score += lithuanian_chars * 2  # Weight Lithuanian characters higher
    
    # Check for common Lithuanian words
    common_lithuanian = ['labas', 'ačiū', 'prašau', 'atsiprašau', 'gerai', 'blogai', 'taip', 'ne']
    for word in common_lithuanian:
        if word in text_lower:
            lithuanian_score += 3
    
    # Determine language based on score
    if lithuanian_score >= 3:
        return "lithuanian"
    elif lithuanian_score >= 1:
        return "likely_lithuanian"
    else:
        return "other"

class BotMetrics:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.average_response_time = 0
        self.start_time = time.time()
        self.audio_requests = 0
        self.text_requests = 0
        self.lithuanian_requests = 0
    
    def record_request(self, success: bool, response_time: float, request_type: str = "text", language: str = "unknown"):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        if request_type == "audio":
            self.audio_requests += 1
        else:
            self.text_requests += 1
        
        if language in ["lithuanian", "likely_lithuanian"]:
            self.lithuanian_requests += 1
        
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
            'text_requests': self.text_requests,
            'audio_requests': self.audio_requests,
            'lithuanian_requests': self.lithuanian_requests,
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Labas! Aš esu GPT-4-powered bot.\n\n"
        "Galiu padėti su:\n"
        "• Bendrais klausimais ir pokalbiais\n"
        "• Balsinių žinučių perrašymu ir stiliaus pagerinimu\n"
        "• Lietuvių kalbos palaikymu\n"
        "• Aukščiausios kokybės AI atsakymais\n\n"
        "Siųsk man bet kokį tekstą ar balsinę žinutę ir atsakysiu!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the /help command is issued."""
    await update.message.reply_text(
        "🤖 Bot komandos:\n\n"
        "💬 Pokalbis:\n"
        "• Siųsk bet kokį tekstą GPT-4 atsakymui\n"
        "• Siųsk balsines žinutes perrašymui + stiliaus pagerinimui\n"
        "• Atsakysiu į jūsų klausimus ir bendrausiu\n\n"
        "🎤 Balsinės funkcijos:\n"
        "• Siųsk balsines žinutes lietuvių ar bet kuria kita kalba\n"
        "• Perrašysiu ir pagerinsiu stilių su GPT-4\n"
        "• Puiku greitiems balsiniams užrašams!\n\n"
        "🚀 Modelis: GPT-4 (su atsarginio plano GPT-3.5-turbo)\n\n"
        "📊 Statistika:\n"
        "• /stats - Peržiūrėk bot veikimo statistiką\n\n"
        "Siųskite man bet kokį tekstą ar balsinę žinutę!"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics (admin feature)."""
    stats = metrics.get_stats()
    stats_message = (
        "📊 Bot statistikos:\n\n"
        f"⏱️ Veikimo laikas: {stats['uptime_hours']:.1f} valandos\n"
        f"📝 Viso užklausų: {stats['total_requests']}\n"
        f"💬 Teksto užklausos: {stats['text_requests']}\n"
        f"🎤 Balsinės užklausos: {stats['audio_requests']}\n"
        f"🇱🇹 Lietuvių kalbos užklausos: {stats['lithuanian_requests']}\n"
        f"✅ Sėkmės procentas: {stats['success_rate']}\n"
        f"⚡ Vidutinis atsakymo laikas: {stats['avg_response_time']}"
    )
    await update.message.reply_text(stats_message)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages: transcribe and improve style."""
    user_id = update.effective_user.id
    start_time = time.time()
    
    # Rate limiting check
    if is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Palaukite akimirką prieš siųsdami kitą žinutę. "
            f"Greitis: {RATE_LIMIT_SECONDS} sekundės tarp žinučių."
        )
        return
    
    try:
        # Get the voice message file
        voice = update.message.voice
        if not voice:
            await update.message.reply_text("❌ Balsinė žinutė nerasta.")
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text("🎤 Apdoruoju jūsų balsinę žinutę...")
        
        # Download the voice file
        file = await context.bot.get_file(voice.file_id)
        
        # Create temporary file for the audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download the file
            await file.download_to_drive(temp_path)
            
            # Transcribe audio using OpenAI Whisper with Lithuanian optimization
            with open(temp_path, "rb") as audio_file:
                transcript_response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="lt",  # Force Lithuanian language detection
                    prompt="Lietuvių kalba, lietuvių kalbos žodžiai, lietuvių kalbos frazės"  # Help Whisper with Lithuanian
                )
            
            transcribed_text = transcript_response.text
            
            if not transcribed_text.strip():
                await update.message.reply_text("❌ Nepavyko perrašyti garso. Bandykite dar kartą aiškiau kalbėdami.")
                return
            
            # Detect language of transcribed text
            detected_language = detect_language(transcribed_text)
            logger.info(f"User {user_id}: Detected language: {detected_language}")
            
            # Update processing message
            await processing_msg.edit_text("✍️ Pagerinu jūsų teksto stilių...")
            
            # Create language-specific style improvement prompt
            if detected_language in ["lithuanian", "likely_lithuanian"]:
                style_prompt = (
                    "Tu esi profesionalus lietuvių kalbos redaktorius ir stiliaus pagerintojas. "
                    "Paimk perrašytą tekstą ir pagerink jį, kad jis būtų profesionaliau, "
                    "aiškiau ir geriau parašytas, išlaikant originalią prasmę. "
                    "Tekstas yra lietuvių kalba - pagerink jį lietuvių kalba. "
                    "Padaryk jį formaliau, aiškiau ir profesionaliau. "
                    "Išlaikyk tą patį ilgį arba šiek tiek ilgesnį, bet daug geresnės kokybės. "
                    "Naudok standartinę lietuvių kalbos gramatiką ir stilių."
                )
            else:
                style_prompt = (
                    "You are a professional language editor and style improver. "
                    "Take the transcribed text and improve it to make it more professional, "
                    "clear, and well-written while maintaining the original meaning. "
                    "Improve it in the same language as the original text. "
                    "Make it more formal, clear, and professional. "
                    "Keep the same length or slightly longer, but much better quality."
                )
            
            messages = [
                {"role": "system", "content": style_prompt},
                {"role": "user", "content": f"Please improve this transcribed text:\n\n{transcribed_text}"}
            ]
            
            # Make API call with retry logic and model fallback for voice processing
            response = None
            current_model = OPENAI_MODEL
            
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.chat.completions.create(
                        model=current_model,
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
                    logger.error(f"OpenAI API error (attempt {attempt + 1}) with model {current_model}: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    else:
                        raise
                except Exception as e:
                    # If GPT-4 fails and we haven't tried fallback yet, switch to GPT-3.5-turbo
                    if current_model == OPENAI_MODEL and OPENAI_MODEL_FALLBACK and attempt < MAX_RETRIES - 1:
                        logger.warning(f"GPT-4 failed for voice processing, falling back to {OPENAI_MODEL_FALLBACK}: {e}")
                        current_model = OPENAI_MODEL_FALLBACK
                        continue
                    else:
                        raise
            
            improved_text = response.choices[0].message.content.strip()
            
            # Create language-specific result message
            if detected_language in ["lithuanian", "likely_lithuanian"]:
                result_message = (
                    "🎤 **Balsinės žinutės rezultatai**\n\n"
                    "📝 **Originalus perrašymas:**\n"
                    f"_{transcribed_text}_\n\n"
                    "✨ **Stiliaus pagerinta versija:**\n"
                    f"{improved_text}"
                )
            else:
                result_message = (
                    "🎤 **Voice Message Results**\n\n"
                    "📝 **Original Transcription:**\n"
                    f"_{transcribed_text}_\n\n"
                    "✨ **Style Improved Version:**\n"
                    f"{improved_text}"
                )
            
            await processing_msg.edit_text(result_message)
            
            # Record metrics
            response_time = time.time() - start_time
            metrics.record_request(True, response_time, "audio", detected_language)
            logger.info(f"User {user_id}: Voice processed in {response_time:.2f}s, language: {detected_language}, model: {current_model}")
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Could not delete temp file {temp_path}: {e}")
        
    except Exception as e:
        error_message = "❌ Klaida apdorojant balsinę žinutę. Bandykite dar kartą."
        if "rate limit" in str(e).lower():
            error_message = "🚫 Viršytas greičio limitas. Bandykite po kelių minučių."
        elif "audio" in str(e).lower():
            error_message = "🔊 Garso apdorojimo klaida. Patikrinkite balsinės žinutės kokybę."
        
        await update.message.reply_text(error_message)
        metrics.record_request(False, time.time() - start_time, "audio", "unknown")
        logger.error(f"Voice processing error for user {user_id}: {e}", exc_info=True)

async def chatgpt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages: send them to OpenAI and reply with the result."""
    user_id = update.effective_user.id
    user_message = update.message.text
    start_time = time.time()
    
    # Rate limiting check
    if is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Palaukite akimirką prieš siųsdami kitą žinutę. "
            f"Greitis: {RATE_LIMIT_SECONDS} sekundės tarp žinučių."
        )
        return
    
    # Detect language of the message
    detected_language = detect_language(user_message)
    logger.info(f"User {user_id}: Text message language detected: {detected_language}")
    
    try:
        # Create language-specific system prompt
        if detected_language in ["lithuanian", "likely_lithuanian"]:
            system_prompt = (
                "Tu esi naudingas ir draugiškas AI asistentas. "
                "Atsakyk natūraliai ir naudingai į vartotojo žinutes. "
                "Atsakymus laikyk glaustus, bet informatyvius. "
                "Vartotojas rašo lietuvių kalba - atsakyk lietuvių kalba. "
                "Būk draugiškas, profesionalus ir naudingas. "
                "Naudok standartinę lietuvių kalbos gramatiką ir stilių."
            )
        else:
            system_prompt = (
                "You are a helpful and friendly AI assistant. "
                "Respond naturally and helpfully to user messages. "
                "Keep responses concise but informative. "
                "If the user writes in Lithuanian, respond in Lithuanian. "
                "If they write in another language, respond in that language."
            )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Make API call with retry logic and model fallback
        response = None
        current_model = OPENAI_MODEL
        
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=current_model,
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
                logger.error(f"OpenAI API error (attempt {attempt + 1}) with model {current_model}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                else:
                    raise
            except Exception as e:
                # If GPT-4 fails and we haven't tried fallback yet, switch to GPT-3.5-turbo
                if current_model == OPENAI_MODEL and OPENAI_MODEL_FALLBACK and attempt < MAX_RETRIES - 1:
                    logger.warning(f"GPT-4 failed, falling back to {OPENAI_MODEL_FALLBACK}: {e}")
                    current_model = OPENAI_MODEL_FALLBACK
                    continue
                else:
                    raise
        
        if response:
            bot_reply = response.choices[0].message.content.strip()
            response_time = time.time() - start_time
            metrics.record_request(True, response_time, "text", detected_language)
            logger.info(f"User {user_id}: Text response in {response_time:.2f}s, language: {detected_language}, model: {current_model}")
        else:
            raise Exception("No response received from OpenAI")
        
    except RateLimitError:
        if detected_language in ["lithuanian", "likely_lithuanian"]:
            bot_reply = "🚫 Viršytas greičio limitas. Bandykite po kelių minučių."
        else:
            bot_reply = "🚫 Rate limit exceeded. Please try again in a few minutes."
        metrics.record_request(False, time.time() - start_time, "text", detected_language)
        logger.warning(f"Rate limit hit for user {user_id}")
    except (APIError, APIConnectionError) as e:
        if detected_language in ["lithuanian", "likely_lithuanian"]:
            bot_reply = "🔌 Paslauga laikinai nepasiekiama. Bandykite vėliau."
        else:
            bot_reply = "🔌 Service temporarily unavailable. Please try again later."
        metrics.record_request(False, time.time() - start_time, "text", detected_language)
        logger.error(f"OpenAI API error for user {user_id}: {e}")
    except Exception as e:
        if detected_language in ["lithuanian", "likely_lithuanian"]:
            bot_reply = "❌ Įvyko netikėta klaida. Bandykite dar kartą."
        else:
            bot_reply = "❌ An unexpected error occurred. Please try again later."
        metrics.record_request(False, time.time() - start_time, "text", detected_language)
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
    
    # Handle voice messages
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    # Handle text messages (exclude commands and voice)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_reply))

    # Start the bot
    logger.info("Bot is starting with optimized chat, voice, and Lithuanian language functionality...")
    
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