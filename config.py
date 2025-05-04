import os
from dotenv import load_dotenv
from logger import setup_logger

# Инициализируем логгер
logger = setup_logger()

# Загружаем переменные окружения
load_dotenv()

# Your testing guild IDs
GUILD_IDS = [889556917901463602]

# The cogs you don't want to load
LOAD_EXCEPTIONS = []

# The directory where your cogs are located
COGS_DIR = "cogs"

# Whether or not the bot should automatically reload cogs when a change is made
AUTO_RELOAD = True

# Twitch configuration
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_NOTIFICATION_CHANNEL_ID = int(os.getenv("TWITCH_NOTIFICATION_CHANNEL_ID", 0))
TWITCH_CHECK_INTERVAL = int(os.getenv("TWITCH_CHECK_INTERVAL", 15))

# Проверяем наличие обязательных переменных
if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
    logger.error("TWITCH_CLIENT_ID или TWITCH_CLIENT_SECRET не установлены в .env файле!")
