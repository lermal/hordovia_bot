import logging
import os

def setup_logger():
    """Настройка системы логирования"""
    
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    logging.getLogger("nextcord").setLevel(logging.WARNING)
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | [%(levelname)s] - %(message)s",
        datefmt="%d.%m.%Y - %H:%M:%S",
        handlers=[
            logging.FileHandler("logs/bot.log", encoding='utf-8'), 
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("bot")