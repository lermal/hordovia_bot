import os
from dotenv import load_dotenv
from utils.settings_manager import SettingsManager
from logger import setup_logger

# Инициализируем логгер
logger = setup_logger()

# Загружаем переменные окружения
load_dotenv()

# Инициализируем менеджер настроек
settings_manager = SettingsManager()

def safe_int(value, default=0):
    """Безопасное преобразование в int с обработкой ошибок"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Не удалось преобразовать '{value}' в int, используется значение по умолчанию: {default}")
        return default

# Your testing guild IDs
GUILD_IDS = [889556917901463602]

# The directory where your cogs are located
COGS_DIR = "cogs"

# Whether or not the bot should automatically reload cogs when a change is made
AUTO_RELOAD = True

# Twitch configuration
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_NOTIFICATION_CHANNEL_ID = safe_int(settings_manager.get_setting("twitch", "notification_channel") or os.getenv("TWITCH_NOTIFICATION_CHANNEL_ID", 0))
TWITCH_CHECK_INTERVAL = safe_int(settings_manager.get_setting("twitch", "check_interval") or os.getenv("TWITCH_CHECK_INTERVAL", 15))

# Музыкальные настройки
AUDIO_FORMAT = settings_manager.get_setting("music", "audio_format") or "mp3"
AUDIO_QUALITY = safe_int(settings_manager.get_setting("music", "audio_quality") or 192)
FFMPEG_PATH = settings_manager.get_setting("music", "ffmpeg_path") or ""

# Общие настройки
LOG_LEVEL = settings_manager.get_setting("general", "log_level") or "INFO"
LOAD_EXCEPTIONS = settings_manager.get_setting("general", "load_exceptions") or []

# Проверяем наличие обязательных переменных
if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
    logger.error("TWITCH_CLIENT_ID или TWITCH_CLIENT_SECRET не установлены в .env файле!")
