import os
from dotenv import load_dotenv
from utils.settings_manager import settings_manager
from logger import setup_logger

# Инициализируем логгер
logger = setup_logger()

# Загружаем переменные окружения
load_dotenv()


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
GUILD_IDS = [889556917901463602, 889556917901463602]

# The directory where your cogs are located
COGS_DIR = "cogs"

# Whether or not the bot should automatically reload cogs when a change is made
AUTO_RELOAD = False

# Twitch configuration
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Функции для получения актуальных настроек
def get_twitch_notification_channel_id():
    return safe_int(settings_manager.get_setting("twitch", "notification_channel") or os.getenv("TWITCH_NOTIFICATION_CHANNEL_ID", 0))

def get_twitch_check_interval():
    return safe_int(settings_manager.get_setting("twitch", "check_interval") or os.getenv("TWITCH_CHECK_INTERVAL", 15))

def get_audio_format():
    return settings_manager.get_setting("music", "audio_format") or "mp3"

def get_audio_quality():
    return safe_int(settings_manager.get_setting("music", "audio_quality") or 192)

def get_ffmpeg_path():
    return settings_manager.get_setting("music", "ffmpeg_path") or ""

def get_log_level():
    return settings_manager.get_setting("general", "log_level") or "INFO"

def get_load_exceptions():
    return settings_manager.get_setting("general", "load_exceptions") or []

# Для обратной совместимости (статические значения)
TWITCH_NOTIFICATION_CHANNEL_ID = get_twitch_notification_channel_id()
TWITCH_CHECK_INTERVAL = get_twitch_check_interval()
AUDIO_FORMAT = get_audio_format()
AUDIO_QUALITY = get_audio_quality()
FFMPEG_PATH = get_ffmpeg_path()
LOG_LEVEL = get_log_level()
LOAD_EXCEPTIONS = get_load_exceptions()

# Проверяем наличие обязательных переменных
if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
    logger.error("TWITCH_CLIENT_ID или TWITCH_CLIENT_SECRET не установлены в .env файле!")
