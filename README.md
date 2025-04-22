## Содержание

- [Введение](#введение)
- [Предварительные требования](#предварительные-требования)
- [Начало работы](#начало-работы)
- [Встроенные функции](#встроенные-функции)
- [Создание когов](#создание-когов)

## Введение

Это шаблон для Discord-бота на Python с использованием библиотеки [Nextcord](https://nextcord.dev/). Он предоставляет базовую структуру для вашего проекта, примеры команд/событий/задач, утилиты и другие компоненты.

## Предварительные требования

- [Python](https://www.python.org/downloads/) 3.8 или новее (Примечание: использование последней версии Python может вызвать [ошибку при установке](https://stackoverflow.com/q/77710589/18072035), поэтому рекомендуется использовать стабильную версию).
- [Аккаунт бота](https://docs.nextcord.dev/en/stable/discord.html) и токен.
- Базовые знания Python и Discord API.

## Начало работы

1. Создайте виртуальное окружение (рекомендуется):
    - Windows: `python -m venv venv`
    - Linux/macOS: `python3 -m venv venv`
2. Активируйте окружение:
    - Windows: `venv\Scripts\activate`
    - Linux/macOS: `source venv/bin/activate`
3. Установите зависимости: `pip install -r requirements.txt`
4. Переименуйте `.env.example` в `.env` и добавьте токен бота.
5. Укажите ID вашего тестового сервера в файле `config.py`.
6. Запустите бота: `python3 main.py`.

## Встроенные функции

### Обработчик когов (Cogs)

Бот использует систему когов для организации команд, событий и задач. Вы можете легко структурировать код в отдельные файлы. Директория с когами настраивается через переменную `COGS_DIR` в `config.py`.

### Автоперезагрузка

Бот может автоматически перезагружать компоненты при изменении кода. Функция включается/выключается через переменную `AUTO_RELOAD` в `config.py`.

### Компоненты интерфейса

- `ConfirmButtons`: Кнопки подтверждения действий.
- `PageButtons`: Пагинация сообщений с навигационными кнопками.

### Логирование

Встроенный класс `Logger` для записи логов в консоль и файл.

## Создание когов

Чтобы создать новый ког:
1. Создайте файл в директории `cogs`.
2. Создайте класс, наследующий `nextcord.ext.commands.Cog`.
3. Добавьте функцию `setup` для регистрации кога.
4. Реализуйте команды/события/задачи.

Примеры:

### Команда

```python
from config import *
from bot import Bot
from nextcord import Interaction, slash_command
from nextcord.ext.commands import Cog

class ExampleCommand(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(description="Пример команды", guild_ids=GUILD_IDS)
    async def example_command(self, interaction: Interaction, ...): # Замените ... на параметры
        pass # Ваш код здесь

def setup(bot: Bot):
    bot.add_cog(ExampleCommand(bot))
```

### Событие

```python
from config import *
from bot import Bot
from nextcord.ext.commands import Cog
from nextcord.ext import commands

class ExampleEvent(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.Cog.listener("имя_события") # Укажите название события
    async def example_event(self, ...): # Параметры события
        pass # Ваш код

def setup(bot: Bot):
    bot.add_cog(ExampleEvent(bot))
```

Список событий: [документация Nextcord](https://nextcord.readthedocs.io/en/latest/api.html#event-reference).

### Задача

```python
from config import *
from bot import Bot
from nextcord.ext.commands import Cog
from nextcord.ext import tasks

class ExampleTask(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
    
    @tasks.loop(seconds=30) # Интервал выполнения
    async def example_task(self):
        await self.bot.wait_until_ready() 
        # Ваш код
                
    @example_task.error
    async def on_error(self, exception: Exception):
        await self.bot.handle_task_error(exception, "example_task")

def setup(bot: Bot):
    bot.add_cog(ExampleTask(bot))
```
