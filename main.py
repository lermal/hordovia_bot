from config import *
from bot import Bot
import nextcord
from dotenv import load_dotenv
import os
from logger import setup_logger

def get_cogs() -> list:
    """Автоматически находит все коги в папке cogs"""
    cogs = []
    for root, _, files in os.walk("cogs"):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                path = os.path.join(root, file[:-3])
                cogs.append(path.replace("/", ".").replace("\\", "."))
    return cogs

def main():
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    logger = setup_logger()
    
    bot = Bot(intents=nextcord.Intents.all())
    bot.logger = logger
    
    load_dotenv()
    token = os.getenv("TOKEN")
    
    if not token:
        bot.logger.critical("Токен не найден в .env файле!")
        exit(1)
    
    load_errors = False 
    
    for cog in get_cogs():  
        try:
            bot.load_extension(cog)
            bot.logger.info(f"Успешно загружен ког: {cog}")
        except Exception as e:
            load_errors = True
            bot.logger.error(f"Ошибка загрузки кога {cog}: {str(e)}")
    
    if not load_errors:
        bot.logger.info("Все коги успешно загружены!")
    
    try:
        bot.run(token)
        
    except nextcord.LoginFailure:
        bot.logger.critical("Неверный токен!")
        exit(1)

if __name__ == "__main__":
    main()