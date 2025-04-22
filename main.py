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
    # Настройка логов
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    logger = setup_logger()
    
    # Инициализация бота
    bot = Bot(intents=nextcord.Intents.all())
    bot.logger = logger
    
    # Загрузка переменных окружения
    load_dotenv()
    token = os.getenv("TOKEN")
    
    if not token:
        bot.logger.critical("Токен не найден в .env файле!")
        exit(1)
    
    # Автозагрузка когов
    load_errors = False  # Флаг для отслеживания ошибок загрузки
    
    for cog in get_cogs():  # Динамическое получение списка
        try:
            bot.load_extension(cog)
            bot.logger.info(f"Успешно загружен ког: {cog}")
        except Exception as e:
            load_errors = True
            bot.logger.error(f"Ошибка загрузки кога {cog}: {str(e)}")
    
    # Выводим итоговое сообщение только если все коги загрузились успешно
    if not load_errors:
        bot.logger.info("Все коги успешно загружены!")
    
    # Запуск бота
    try:
        bot.run(token)
    except nextcord.LoginFailure:
        bot.logger.critical("Неверный токен!")
        exit(1)

if __name__ == "__main__":
    main()