# Optimized Telegram Chat Bot

A high-performance Telegram bot powered by OpenAI's GPT-3.5-turbo with built-in optimizations.

## 🚀 Features

- **ChatGPT Integration**: Powered by OpenAI's GPT-3.5-turbo
- **Rate Limiting**: Prevents spam with configurable limits
- **Retry Logic**: Automatic retry on API failures
- **Performance Metrics**: Track response times and success rates
- **Error Handling**: Graceful error handling with user-friendly messages
- **Resource Management**: Optimized memory and connection usage

## ⚙️ Configuration

Create a `.env` file with the following variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# Optional Performance Settings (defaults shown)
RATE_LIMIT_SECONDS=2      # Minimum seconds between messages per user
MAX_RETRIES=3             # Maximum API retry attempts
RETRY_DELAY=1             # Delay between retries in seconds
OPENAI_TIMEOUT=30         # API timeout in seconds
MAX_TOKENS=500            # Maximum response tokens
TEMPERATURE=0.7           # AI response creativity (0.0-1.0)
```

## 📊 Commands

- `/start` - Welcome message
- `/help` - Show available commands
- `/stats` - View bot performance statistics

## 🔧 Optimizations Implemented

### Performance
- **Connection Pooling**: Optimized OpenAI client with timeout and retry settings
- **Rate Limiting**: Per-user message throttling to prevent abuse
- **Response Caching**: Efficient message processing
- **Memory Management**: Optimized data structures and cleanup

### Reliability
- **Retry Logic**: Automatic retry on transient failures
- **Error Categorization**: Different handling for different error types
- **Graceful Degradation**: User-friendly error messages
- **Circuit Breaker**: Prevents cascading failures

### Monitoring
- **Real-time Metrics**: Track response times, success rates, and uptime
- **Structured Logging**: Comprehensive logging for debugging
- **Performance Tracking**: Monitor bot health and performance

## 🚀 Running the Bot

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`

3. Run the bot:
   ```bash
   python main.py
   ```

## 📈 Performance Benefits

- **Faster Response Times**: Optimized API calls and connection handling
- **Better Resource Usage**: Efficient memory and CPU utilization
- **Higher Reliability**: Automatic retry and error handling
- **Scalability**: Rate limiting and resource management for high traffic
- **Monitoring**: Real-time insights into bot performance
