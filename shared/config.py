import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Bot Settings
BOT_NAME = "Simple Chat Bot"
BOT_VERSION = "1.0.0"

# Performance & Rate Limiting
RATE_LIMIT_SECONDS = int(os.getenv('RATE_LIMIT_SECONDS', '2'))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
RETRY_DELAY = int(os.getenv('RETRY_DELAY', '1'))
OPENAI_TIMEOUT = int(os.getenv('OPENAI_TIMEOUT', '30'))
MAX_TOKENS = int(os.getenv('MAX_TOKENS', '500'))
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO' 