# Optimized Telegram Chat Bot with Voice Support

A high-performance Telegram bot powered by OpenAI's GPT-3.5-turbo and Whisper, featuring voice message transcription and style improvement with special support for Lithuanian language.

## 🚀 Features

- **ChatGPT Integration**: Powered by OpenAI's GPT-3.5-turbo
- **🎤 Voice Message Processing**: Transcribe voice messages to text
- **✨ Style Improvement**: Enhance transcribed text quality and professionalism
- **🇱🇹 Lithuanian Language Support**: Optimized for Lithuanian voice input
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

- `/start` - Welcome message with feature overview
- `/help` - Show available commands and voice features
- `/stats` - View bot performance statistics including voice/text request counts

## 🎤 Voice Message Features

### How It Works:
1. **Send a voice message** in any language (optimized for Lithuanian)
2. **Automatic transcription** using OpenAI Whisper
3. **Style improvement** using ChatGPT for professional, clear text
4. **Dual output** showing both original transcription and improved version

### Voice Processing Flow:
```
🎤 Voice Message → 📝 Transcription → ✨ Style Improvement → 📋 Results
```

### Supported Languages:
- **🇱🇹 Lithuanian** (optimized with language detection)
- **🌍 All other languages** (automatic detection)

## 🔧 Optimizations Implemented

### Performance
- **Connection Pooling**: Optimized OpenAI client with timeout and retry settings
- **Rate Limiting**: Per-user message throttling to prevent abuse
- **Response Caching**: Efficient message processing
- **Memory Management**: Optimized data structures and cleanup
- **Audio Processing**: Efficient voice file handling with temporary file cleanup

### Reliability
- **Retry Logic**: Automatic retry on transient failures
- **Error Categorization**: Different handling for different error types
- **Graceful Degradation**: User-friendly error messages
- **Circuit Breaker**: Prevents cascading failures
- **File Cleanup**: Automatic temporary file removal

### Monitoring
- **Real-time Metrics**: Track response times, success rates, and uptime
- **Request Type Tracking**: Separate metrics for text vs. voice requests
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
- **Voice Processing**: Efficient audio transcription and style improvement

## 🎯 Use Cases

### Perfect For:
- **Quick voice notes** that need professional formatting
- **Meeting transcriptions** with style improvement
- **Language learning** with instant feedback
- **Professional communication** enhancement
- **Lithuanian language** voice processing

### Example Workflow:
1. Record a voice message in Lithuanian
2. Bot transcribes it automatically
3. Bot improves the style and professionalism
4. Get both versions for comparison
5. Use the improved text for professional communication
