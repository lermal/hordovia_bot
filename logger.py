import logging
import os

def setup_logger():
    """Настройка системы логирования"""
    
    # Создаем директорию для логов если её нет
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    # Отключаем системные логи nextcord
    logging.getLogger("nextcord").setLevel(logging.WARNING)
    
    # Настройка базового логгера
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | [%(levelname)s] - %(message)s",
        datefmt="%d.%m.%Y - %H:%M:%S",
        handlers=[
            logging.FileHandler("logs/bot.log"),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("bot")