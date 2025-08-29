# Optimized Telegram Chat Bot with Voice Support

A high-performance Telegram bot powered by **OpenAI's GPT-4** and Whisper, featuring voice message transcription and style improvement with special support for Lithuanian language.

## 🚀 Features

- **🚀 GPT-4 Integration**: Powered by OpenAI's latest and most advanced AI model
- **🎤 Voice Message Processing**: Transcribe voice messages to text
- **✨ Style Improvement**: Enhance transcribed text quality and professionalism
- **🇱🇹 Lithuanian Language Support**: Optimized for Lithuanian voice input
- **🔄 Smart Fallback**: Automatic fallback to GPT-3.5-turbo if GPT-4 fails
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

- `/start` - Welcome message with feature overview
- `/help` - Show available commands and voice features
- `/stats` - View bot performance statistics including voice/text request counts

## 🎤 Voice Message Features

### How It Works:
1. **Send a voice message** in any language (optimized for Lithuanian)
2. **Automatic transcription** using OpenAI Whisper
3. **Style improvement** using GPT-4 for professional, clear text
4. **Dual output** showing both original transcription and improved version

### Voice Processing Flow:
```
🎤 Voice Message → 📝 Transcription → ✨ GPT-4 Style Improvement → 📋 Results
```

### Supported Languages:
- **🇱🇹 Lithuanian** (optimized with language detection)
- **🌍 All other languages** (automatic detection)

## 🚀 GPT-4 Benefits

### Superior Quality:
- **Better voice transcription** understanding and context
- **Higher quality style improvements** for professional text
- **Enhanced Lithuanian language** processing and grammar
- **More natural and fluent** responses
- **Better context preservation** while improving style

### Smart Fallback System:
- **Primary**: GPT-4 for maximum quality
- **Fallback**: GPT-3.5-turbo if GPT-4 fails
- **Automatic switching** without user intervention
- **Cost optimization** when needed

## 🔧 Optimizations Implemented

### Performance
- **Connection Pooling**: Optimized OpenAI client with timeout and retry settings
- **Rate Limiting**: Per-user message throttling to prevent abuse
- **Response Caching**: Efficient message processing
- **Memory Management**: Optimized data structures and cleanup
- **Audio Processing**: Efficient voice file handling with temporary file cleanup
- **Model Fallback**: Automatic fallback to ensure reliability

### Reliability
- **Retry Logic**: Automatic retry on transient failures
- **Error Categorization**: Different handling for different error types
- **Graceful Degradation**: User-friendly error messages
- **Circuit Breaker**: Prevents cascading failures
- **File Cleanup**: Automatic temporary file removal
- **Smart Fallback**: GPT-3.5-turbo backup when GPT-4 fails

### Monitoring
- **Real-time Metrics**: Track response times, success rates, and uptime
- **Request Type Tracking**: Separate metrics for text vs. voice requests
- **Language Tracking**: Monitor Lithuanian vs. other language usage
- **Model Usage Tracking**: Log which model was used for each request
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
- **GPT-4 Quality**: Superior AI responses and voice processing
- **Smart Fallback**: Reliable operation even when GPT-4 is unavailable

## 🎯 Use Cases

### Perfect For:
- **Quick voice notes** that need professional formatting
- **Meeting transcriptions** with style improvement
- **Language learning** with instant feedback
- **Professional communication** enhancement
- **Lithuanian language** voice processing
- **High-quality AI conversations** with GPT-4

### Example Workflow:
1. Record a voice message in Lithuanian
2. Bot transcribes it automatically with Whisper
3. Bot improves the style using GPT-4
4. Get both versions for comparison
5. Use the improved text for professional communication

## 💰 Cost Considerations

### GPT-4 Pricing:
- **Input**: $0.03 per 1K tokens (20x more expensive than GPT-3.5)
- **Output**: $0.06 per 1K tokens (30x more expensive than GPT-3.5)
- **Voice**: Same cost (Whisper pricing unchanged)

### Cost Optimization:
- **Smart fallback** to GPT-3.5-turbo when needed
- **Configurable token limits** to control costs
- **Efficient prompting** to minimize token usage
- **Automatic model selection** based on availability
