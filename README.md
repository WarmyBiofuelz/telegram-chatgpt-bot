# Personal Horoscope Bot 🌟

A personalized Telegram bot that generates daily horoscopes using OpenAI's GPT-4, featuring user registration, multilingual support, and automated daily delivery.

## 🚀 Features

- **🌟 Personalized Horoscopes**: AI-generated horoscopes based on user profile
- **📝 User Registration**: Interactive questionnaire to create personal profiles
- **🌍 Multilingual Support**: Lithuanian (LT), English (EN), and Russian (RU)
- **📅 Daily Automation**: Automatic horoscope delivery every morning at 07:30
- **💾 User Profiles**: SQLite database to store user information
- **🎯 GPT-4 Powered**: High-quality, personalized horoscope generation
- **🔄 Smart Fallback**: Automatic fallback to GPT-3.5-turbo if needed
- **⚡ Modern Architecture**: Built with python-telegram-bot and async/await

## ⚙️ Configuration

Create a `.env` file with the following variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# OpenAI Model Configuration (Optional - defaults shown)
OPENAI_MODEL=gpt-4                    # Primary model (GPT-4)
OPENAI_MODEL_FALLBACK=gpt-3.5-turbo  # Fallback model if GPT-4 fails

# Optional Performance Settings (defaults shown)
RATE_LIMIT_SECONDS=2      # Minimum seconds between messages per user
MAX_RETRIES=3             # Maximum API retry attempts
RETRY_DELAY=1             # Delay between retries in seconds
OPENAI_TIMEOUT=30         # API timeout in seconds
MAX_TOKENS=1000           # Maximum response tokens (increased for GPT-4)
TEMPERATURE=0.7           # AI response creativity (0.0-1.0)
```

## 📊 Commands

- `/start` - Begin user registration process
- `/horoscope` - Get today's personalized horoscope
- `/profile` - View your profile information
- `/help` - Show help information
- `/cancel` - Cancel current registration process

## 🎯 How It Works

### User Registration Flow:
1. **Start Registration**: User sends `/start`
2. **Profile Creation**: Bot asks 7 questions:
   - Name
   - Birthday (YYYY-MM-DD format)
   - Preferred language (LT/EN/RU)
   - Profession
   - Hobbies
   - Gender (moteris/vyras)
   - Main interests
3. **Profile Storage**: Data saved to SQLite database
4. **Confirmation**: User receives confirmation and available commands

### Daily Horoscope Generation:
1. **Scheduled Delivery**: Every day at 07:30 AM
2. **User Retrieval**: Bot fetches all registered users
3. **Personalized Generation**: GPT-4 creates unique horoscope for each user
4. **Language-Specific**: Horoscopes generated in user's preferred language
5. **Automatic Sending**: Horoscopes delivered to all users

### Horoscope Features:
- **Personalized Content**: Based on user's profile data
- **Motivational Tone**: Positive and uplifting messages
- **Practical Advice**: Actionable recommendations
- **Fresh Content**: Never repetitive, always unique
- **Appropriate Length**: 3-4 sentences for optimal reading

## 🗄️ Database Schema

The bot uses SQLite with the following user table:

```sql
CREATE TABLE users (
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
```

## 🔧 Technical Features

### Architecture:
- **Async/Await**: Modern Python async programming
- **Conversation Handler**: Multi-step user registration
- **Database Integration**: SQLite for user data persistence
- **Scheduling**: Background thread for daily horoscope delivery
- **Error Handling**: Comprehensive error management and logging

### Performance:
- **Rate Limiting**: Prevents spam and abuse
- **Retry Logic**: Automatic retry on API failures
- **Model Fallback**: GPT-3.5-turbo backup when GPT-4 fails
- **Efficient Database**: Optimized SQLite queries
- **Background Processing**: Non-blocking scheduler

### Security:
- **Input Validation**: Date format and option validation
- **SQL Injection Protection**: Parameterized queries
- **Error Sanitization**: Safe error messages
- **Rate Limiting**: Protection against abuse

## 🚀 Running the Bot

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Up Environment**:
   Create `.env` file with your API keys

3. **Run the Bot**:
   ```bash
   python main.py
   ```

4. **Test Registration**:
   - Send `/start` to your bot
   - Complete the registration process
   - Test `/horoscope` command

## 📈 Usage Examples

### Registration Process:
```
User: /start
Bot: Labas! Aš esu tavo asmeninis horoskopų botukas 🌟
     Atsakyk į kelis klausimus, kad galėčiau pritaikyti horoskopą būtent tau.
     Pradėkime nuo tavo vardo:

User: Jonas
Bot: Puiku, Jonas! 🌟
     Dabar pasakyk savo gimimo datą (formatas: YYYY-MM-DD):

User: 1990-05-15
Bot: Puiku! 📅
     Kokia kalba nori gauti horoskopą?
     • LT - Lietuvių kalba
     • EN - English
     • RU - Русский
```

### Horoscope Generation:
```
User: /horoscope
Bot: Generuoju tavo asmeninį horoskopą... ✨

Bot: 🌟 **Jonas, šiandien tau laukia puikių galimybių!** 
     Tavo profesinis patirimas ir kūrybiškumas bus ypač vertinami. 
     Neišsigąsk imtis naujų iššūkių - jie atneš ne tik sėkmę, 
     bet ir asmeninį pasitenkinimą. Šiandien ypač tinkamas laikas 
     planuoti keliones ar domėtis naujais pomėgiais! ✨
```

## 💰 Cost Considerations

### GPT-4 Pricing:
- **Input**: $0.03 per 1K tokens
- **Output**: $0.06 per 1K tokens
- **Daily Cost**: ~$0.10-0.50 per 100 users (depending on horoscope length)

### Cost Optimization:
- **Smart Fallback**: Automatic switch to GPT-3.5-turbo when needed
- **Token Limits**: Configurable response length
- **Efficient Prompts**: Optimized for minimal token usage
- **Daily Limits**: One horoscope per user per day

## 🎯 Use Cases

### Perfect For:
- **Personal Use**: Daily motivation and guidance
- **Wellness Apps**: Mental health and positivity
- **Language Learning**: Multilingual content delivery
- **Community Building**: Engaging user interaction
- **Content Creation**: Automated personalized content

### Target Audience:
- **Horoscope Enthusiasts**: People who enjoy daily horoscopes
- **Multilingual Users**: Lithuanian, English, and Russian speakers
- **Wellness Seekers**: Those looking for daily motivation
- **Tech-Savvy Users**: Comfortable with Telegram bots

## 🔮 Future Enhancements

### Planned Features:
- **Zodiac Sign Integration**: Astrological calculations
- **Weekly/Monthly Horoscopes**: Extended time periods
- **Custom Timing**: User-defined delivery times
- **Horoscope History**: Past horoscope access
- **Social Features**: Share horoscopes with friends
- **Premium Features**: Advanced personalization

### Technical Improvements:
- **Web Dashboard**: Admin panel for user management
- **Analytics**: User engagement tracking
- **A/B Testing**: Horoscope style optimization
- **Caching**: Improved performance
- **Scalability**: Support for larger user bases

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For support, please open an issue on GitHub or contact the development team.