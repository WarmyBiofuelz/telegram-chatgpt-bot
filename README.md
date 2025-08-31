# Horoscope Bot - Separated Architecture 🌟

A multilingual Telegram bot system that provides personalized horoscopes using OpenAI's GPT-4o model. The system is now split into two focused bots for better maintainability and scalability.

## 🏗️ Architecture

The bot system consists of two separate components:

### 1. Registration Bot (`registration_bot.py`)
- **Purpose**: Handles user registration and database management
- **Features**: User onboarding, data collection, profile management
- **Commands**: `/start`, `/reset`, `/help`

### 2. Horoscope Bot (`horoscope_bot.py`)
- **Purpose**: Generates and sends horoscopes from database data
- **Features**: Horoscope generation, daily delivery, profile viewing
- **Commands**: `/horoscope`, `/profile`, `/help`

## 🚀 Features

- **🌟 Personalized Horoscopes**: AI-generated horoscopes based on user profile
- **📝 User Registration**: Interactive questionnaire to create personal profiles
- **🌍 Multilingual Support**: Lithuanian (LT), English (EN), Russian (RU), Latvian (LV)
- **📅 Daily Automation**: Automatic horoscope delivery every morning at 07:30
- **💾 User Profiles**: SQLite database to store user information
- **🎯 GPT-4o Powered**: High-quality, personalized horoscope generation
- **♈ Zodiac Integration**: Automatic zodiac sign calculation and integration
- **⚡ Separated Architecture**: Independent bots for better maintainability
- **🔄 Rate Limiting**: Prevents spam and abuse

## 📊 Commands

### Registration Bot
- `/start` - Start registration process
- `/reset` - Reset your data and re-register
- `/help` - Show help information

### Horoscope Bot
- `/horoscope` - Get today's horoscope
- `/profile` - View your profile
- `/help` - Show help information

## 🎯 Registration Process

1. **Language Selection** - Choose your preferred language (LT/EN/RU/LV)
2. **Name** - Enter your name
3. **Gender** - Select your gender (woman/man, moteris/vyras, etc.)
4. **Birthday** - Enter your birth date (YYYY-MM-DD format)
5. **Profession** - Enter your profession
6. **Hobbies** - Enter your hobbies

## ⚙️ Configuration

Create a `.env` file with the following variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# OpenAI Model Configuration (Optional - defaults shown)
OPENAI_MODEL=gpt-4o-2024-05-13    # Primary model (GPT-4o)

# Optional Performance Settings (defaults shown)
RATE_LIMIT_SECONDS=2      # Minimum seconds between messages per user
MAX_RETRIES=3             # Maximum API retry attempts
RETRY_DELAY=1             # Delay between retries in seconds
OPENAI_TIMEOUT=30         # API timeout in seconds
MAX_TOKENS=1000           # Maximum response tokens
TEMPERATURE=0.7           # AI response creativity (0.0-1.0)
LOG_LEVEL=INFO            # Logging level
```

## 🚀 Running the Bots

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Up Environment**:
   Create `.env` file with your API keys

3. **Run the Bots**:

   **Option 1: Run Registration Bot Only**
   ```bash
   python start_registration_bot.py
   ```

   **Option 2: Run Horoscope Bot Only**
   ```bash
   python start_horoscope_bot.py
   ```

   **Option 3: Run Both Bots (Separate Terminals)**
   ```bash
   # Terminal 1
   python start_registration_bot.py

   # Terminal 2
   python start_horoscope_bot.py
   ```

**Note**: The old `main.py` file has been removed as it's no longer needed with the separated architecture.

## 🗄️ Database Schema

The bots share a SQLite database with the following schema:

```sql
CREATE TABLE users (
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
);
```

## 🎯 How It Works

### User Registration Flow:
1. **Start Registration**: User sends `/start` to Registration Bot
2. **Profile Creation**: Bot asks 6 questions in user's selected language
3. **Profile Storage**: Data saved to shared SQLite database
4. **Confirmation**: User receives confirmation and available commands

### Daily Horoscope Generation:
1. **Scheduled Delivery**: Horoscope Bot runs daily at 07:30 AM
2. **User Retrieval**: Bot fetches all registered users from database
3. **Personalized Generation**: GPT-4o creates unique horoscope for each user
4. **Zodiac Integration**: Automatic zodiac sign calculation and integration
5. **Language-Specific**: Horoscopes generated in user's preferred language
6. **Automatic Sending**: Horoscopes delivered to all users

### Horoscope Features:
- **Personalized Content**: Based on user's profile data and zodiac sign
- **Psychological Insights**: Deep understanding of user's personality
- **Practical Advice**: Actionable recommendations
- **Fresh Content**: Never repetitive, always unique
- **Optimal Length**: 4-5 sentences for comprehensive guidance

## 🔧 Technical Features

### Architecture:
- **Separated Bots**: Independent bots for registration and horoscope delivery
- **Async/Await**: Modern Python async programming
- **Conversation Handler**: Multi-step user registration
- **Database Integration**: Shared SQLite for user data persistence
- **Scheduling**: Background thread for daily horoscope delivery
- **Error Handling**: Comprehensive error management and logging

### Performance:
- **Rate Limiting**: Prevents spam and abuse
- **Retry Logic**: Automatic retry on API failures
- **Efficient Database**: Optimized SQLite queries with WAL mode
- **Background Processing**: Non-blocking scheduler
- **Connection Pooling**: Optimized database connections

### Security:
- **Input Validation**: Comprehensive validation for all fields
- **SQL Injection Protection**: Parameterized queries
- **Error Sanitization**: Safe error messages
- **Rate Limiting**: Protection against abuse
- **Data Sanitization**: Input cleaning and length limits

## 💡 Benefits of Separated Architecture

- **Better Maintainability**: Each bot has a single responsibility
- **Independent Scaling**: Can scale each bot independently
- **Easier Debugging**: Issues are isolated to specific functionality
- **Flexible Deployment**: Can deploy bots on different servers
- **Resource Optimization**: Each bot only loads what it needs
- **Fault Tolerance**: One bot failure doesn't affect the other

## 📈 Usage Examples

### Registration Process:
```
User: /start
Bot: 🇱🇹 Rašyk LT lietuviškai
     🇬🇧 Type EN for English
     🇷🇺 Напиши RU по-русски
     🇱🇻 Raksti LV latviešu valodā

User: EN
Bot: Hello! I'm your personal horoscope bot 🌟
     Answer a few questions so I can personalize your horoscope.
     
     Great! 🌟
     What is your name?

User: John
Bot: Great! 🌟
     What is your gender? (woman/man)
```

### Horoscope Generation:
```
User: /horoscope
Bot: 🔮 Generating your personal horoscope...

Bot: 🌟 **John's horoscope for today:**
     Today brings excellent opportunities for professional growth, John. 
     Your creative energy is particularly strong, making it an ideal time 
     to pursue new projects or share innovative ideas. The stars suggest 
     that your communication skills will be especially effective today, 
     so don't hesitate to reach out to colleagues or present your thoughts. 
     Trust your intuition when making decisions, as it's aligned with 
     your Aries nature and will guide you toward success.
```

## 💰 Cost Considerations

### GPT-4o Pricing:
- **Input**: $0.005 per 1K tokens
- **Output**: $0.015 per 1K tokens
- **Daily Cost**: ~$0.05-0.20 per 100 users (depending on horoscope length)

### Cost Optimization:
- **Token Limits**: Configurable response length
- **Efficient Prompts**: Optimized for minimal token usage
- **Daily Limits**: One horoscope per user per day
- **Smart Caching**: Reduced redundant API calls

## 🎯 Use Cases

### Perfect For:
- **Personal Use**: Daily motivation and guidance
- **Wellness Apps**: Mental health and positivity
- **Language Learning**: Multilingual content delivery
- **Community Building**: Engaging user interaction
- **Content Creation**: Automated personalized content
- **Scalable Services**: Handle growing user bases efficiently

### Target Audience:
- **Horoscope Enthusiasts**: People who enjoy daily horoscopes
- **Multilingual Users**: Lithuanian, English, Russian, and Latvian speakers
- **Wellness Seekers**: Those looking for daily motivation
- **Tech-Savvy Users**: Comfortable with Telegram bots

## 🔮 Future Enhancements

### Planned Features:
- **Weekly/Monthly Horoscopes**: Extended time periods
- **Custom Timing**: User-defined delivery times
- **Horoscope History**: Past horoscope access
- **Social Features**: Share horoscopes with friends
- **Premium Features**: Advanced personalization
- **Web Dashboard**: Admin panel for user management

### Technical Improvements:
- **Analytics**: User engagement tracking
- **A/B Testing**: Horoscope style optimization
- **Caching**: Improved performance
- **Microservices**: Further architecture separation
- **API Gateway**: Centralized bot management

## 🔄 Migration from Single Bot

If you're migrating from the single `main.py` bot:

1. **Stop the old bot**
2. **The database schema is automatically migrated**
3. **Start the new separated bots**
4. **All existing user data is preserved**

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For support, please open an issue on GitHub or contact the development team.