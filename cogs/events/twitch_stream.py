from config import *
from bot import Bot
from nextcord import Embed, Color, ui, ButtonStyle
from nextcord.ext.commands import Cog
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import os
from logger import setup_logger

logger = setup_logger()

class TwitchStream(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.streaming = {}
        self.access_token = None
        self.token_expires_at = None
        self.task = None
        self.streamers_file = "data/streamers.json"
        self.token_file = "data/twitch_token.json"
        self.state_file = "data/twitch_state.json"  # Файл для сохранения состояния
        self.stream_messages = {}  # Словарь для хранения ID сообщений о стримах
        self.stream_categories = {}  # Словарь для хранения текущих категорий стримов
        self.pending_deletions = {}  # Словарь для хранения задач на удаление сообщений
        self.avatar_cache = {}
        
        # Загружаем сохраненное состояние
        self.load_state()
        
        # Запускаем задачу при инициализации
        self.task = self.bot.loop.create_task(self.twitch_check_loop())
        # Загружаем сохраненный токен
        self.load_token()

        # Загружаем кэш аватарок
        self.load_avatar_cache()

    def load_state(self):
        """Загрузка сохраненного состояния"""
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(self.state_file):
            return
            
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.stream_messages = data.get("stream_messages", {})
                self.stream_categories = data.get("stream_categories", {})
                self.streaming = data.get("streaming", {})
                logger.info("Twitch: Состояние загружено")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при загрузке состояния: {e}")

    def save_state(self):
        """Сохранение текущего состояния"""
        try:
            data = {
                "stream_messages": self.stream_messages,
                "stream_categories": self.stream_categories,
                "streaming": self.streaming
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Twitch: Ошибка при сохранении состояния: {e}")

    def load_token(self):
        """Загрузка сохраненного токена из файла"""
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(self.token_file):
            return
            
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.access_token = data.get("access_token")
                expires_at = data.get("expires_at")
                if expires_at:
                    self.token_expires_at = datetime.fromisoformat(expires_at)
                    
                # Проверяем, не истек ли токен
                if self.token_expires_at and datetime.now() >= self.token_expires_at:
                    logger.error("Twitch: Токен истек, требуется новый")
                    self.access_token = None
                    self.token_expires_at = None
                else:
                    logger.info("Twitch: Загружен сохраненный токен")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при загрузке токена: {e}")
            self.access_token = None
            self.token_expires_at = None

    def save_token(self, access_token: str, expires_in: int):
        """Сохранение токена в файл"""
        try:
            self.access_token = access_token
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            data = {
                "access_token": access_token,
                "expires_at": self.token_expires_at.isoformat()
            }
            
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            logger.info(f"Twitch: Токен сохранен, срок действия до {self.token_expires_at}")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при сохранении токена: {e}")

    def load_streamers(self):
        """Загрузка списка стримеров из файла"""
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(self.streamers_file):
            with open(self.streamers_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        with open(self.streamers_file, "r", encoding="utf-8") as f:
            return json.load(f)

    async def get_access_token(self):
        """Получение нового токена доступа"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://id.twitch.tv/oauth2/token',
                    params={
                        'client_id': TWITCH_CLIENT_ID,
                        'client_secret': TWITCH_CLIENT_SECRET,
                        'grant_type': 'client_credentials'
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.save_token(data['access_token'], data['expires_in'])
                    else:
                        error_data = await response.json()
                        logger.error(f"Twitch: Ошибка получения токена: {response.status}")
                        logger.error(f"Twitch: Ответ сервера: {error_data}")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при получении токена: {e}")
            logger.error(f"Twitch: Проверьте значения TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET в .env файле")

    async def check_stream_status(self):
        """Проверка статуса стрима"""
        try:
            # Добавляем диагностическое логирование
            logger.debug(f"Twitch: TWITCH_CHECK_INTERVAL = {TWITCH_CHECK_INTERVAL} (тип: {type(TWITCH_CHECK_INTERVAL)})")
            logger.debug(f"Twitch: TWITCH_NOTIFICATION_CHANNEL_ID = {TWITCH_NOTIFICATION_CHANNEL_ID} (тип: {type(TWITCH_NOTIFICATION_CHANNEL_ID)})")
            
            # Проверяем срок действия токена
            if not self.access_token or datetime.now() >= self.token_expires_at:
                await self.get_access_token()

            # Загружаем актуальный список стримеров
            streamers = self.load_streamers()
            if not streamers:
                return

            # Формируем запрос для всех стримеров
            user_logins = [channel for channel, data in streamers.items() if data["enabled"]]
            
            # Фильтруем пустые логины
            user_logins = [login for login in user_logins if login and login.strip()]
            
            if not user_logins:
                logger.debug("Twitch: Нет активных стримеров для проверки")
                return

            # Разбиваем на части, если стримеров больше 100 (лимит Twitch API)
            chunk_size = 100
            user_login_chunks = [user_logins[i:i + chunk_size] for i in range(0, len(user_logins), chunk_size)]
            
            active_streams = {}
            
            for chunk in user_login_chunks:
                await self._check_stream_chunk(chunk, active_streams, streamers)
            
            # Обрабатываем результаты после всех чанков
            for channel, streamer_data in streamers.items():
                if not streamer_data["enabled"]:
                    continue
                    
                is_streaming = channel in active_streams
                was_streaming = channel in self.streaming
                
                if is_streaming and not was_streaming:
                    logger.info(f"Twitch: Стрим начался у {channel}")
                    await self.on_stream_start(channel, active_streams[channel], streamer_data["description"])
                    self.streaming[channel] = True
                    self.save_state()
                elif not is_streaming and was_streaming:
                    logger.info(f"Twitch: Стрим закончился у {channel}")
                    await self.on_stream_end(channel, streamer_data["description"])
                    del self.streaming[channel]
                    self.save_state()
                elif is_streaming and was_streaming:
                    # Проверяем изменение категории
                    current_category = active_streams[channel]['game_name']
                    if current_category != self.stream_categories.get(channel):
                        logger.info(f"Twitch: У {channel} изменилась категория на {current_category}")
                        await self.update_stream_category(channel, active_streams[channel])
        except Exception as e:
            logger.error(f"Twitch: Ошибка при проверке стрима: {e}")
            import traceback
            logger.error(f"Twitch: Полный стек ошибки: {traceback.format_exc()}")

    async def _check_stream_chunk(self, chunk, active_streams, streamers):
        async with aiohttp.ClientSession() as session:
            # Формируем URL запроса с повторяющимися параметрами user_login
            params = []
            for login in chunk:
                params.append(f"user_login={login}")
            url = f"https://api.twitch.tv/helix/streams?{'&'.join(params)}"
            
            headers = {
                'Client-ID': TWITCH_CLIENT_ID,
                'Authorization': f'Bearer {self.access_token}'
            }
            
            logger.debug(f"Twitch: Отправляем запрос к {url}")
            logger.debug(f"Twitch: Заголовки: {headers}")
            logger.debug(f"Twitch: Стримеры для проверки: {chunk}")
            
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    active_streams.update({stream['user_login'].lower(): stream for stream in data['data']})
                else:
                    error_text = await response.text()
                    logger.error(f"Twitch: Ошибка проверки стрима: {response.status}")
                    logger.error(f"Twitch: URL запроса: {url}")
                    logger.error(f"Twitch: Заголовки запроса: {headers}")
                    logger.error(f"Twitch: Ответ сервера: {error_text}")
                    
                    # Если токен истек или недействителен, получаем новый
                    if response.status == 401:
                        logger.info("Twitch: Токен недействителен, получаем новый")
                        await self.get_access_token()
                    elif response.status == 400:
                        logger.error("Twitch: Неправильный запрос. Проверьте параметры запроса.")
                        # Проверяем, не слишком ли много стримеров в запросе
                        if len(chunk) > 100:
                            logger.error("Twitch: Слишком много стримеров в одном запросе (максимум 100)")
                        # Проверяем, нет ли пустых логинов
                        empty_logins = [login for login in chunk if not login.strip()]
                        if empty_logins:
                            logger.error(f"Twitch: Найдены пустые логины: {empty_logins}")

    async def get_user_avatar(self, login):
        """Получить URL аватарки стримера по логину с кэшированием"""
        if login in self.avatar_cache:
            return self.avatar_cache[login]
        try:
            if not self.access_token or datetime.now() >= self.token_expires_at:
                await self.get_access_token()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.twitch.tv/helix/users?login={login}",
                    headers={
                        'Client-ID': TWITCH_CLIENT_ID,
                        'Authorization': f'Bearer {self.access_token}'
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data['data']:
                            avatar_url = data['data'][0]['profile_image_url']
                            self.avatar_cache[login] = avatar_url
                            self.save_avatar_cache()
                            return avatar_url
            return None
        except Exception as e:
            logger.error(f"Twitch: Ошибка при получении аватарки: {e}")
            return None

    async def on_stream_start(self, channel, stream_data, description):
        """Действия при начале стрима"""
        try:
            # Получаем канал для уведомлений
            notification_channel = self.bot.get_channel(TWITCH_NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                logger.error("Twitch: Канал для уведомлений не найден")
                return

            # Получаем аватарку стримера
            avatar_url = await self.get_user_avatar(channel)

            # Загружаем данные стримера для получения текста уведомления
            streamers = self.load_streamers()
            streamer_data = streamers.get(channel, {})
            notification_text = streamer_data.get("notification_text", "")

            # Проверяем, есть ли уже сообщение о стриме
            message_id = self.stream_messages.get(channel)
            if message_id:
                try:
                    message = await notification_channel.fetch_message(message_id)
                    if message:
                        if channel in self.pending_deletions:
                            self.pending_deletions[channel].cancel()
                            del self.pending_deletions[channel]
                        # Формируем embed с описанием и категорией
                        embed = message.embeds[0]
                        embed.description = f"{description}\n\n**Категория:** {stream_data['game_name']}"
                        embed.color = 0x9146FF
                        if avatar_url:
                            embed.set_thumbnail(url=avatar_url)
                        view = ui.View()
                        button = ui.Button(label="Перейти на канал", url=f"https://twitch.tv/{channel}", style=ButtonStyle.url)
                        view.add_item(button)
                        
                        # Отправляем текст уведомления отдельно, если он есть
                        if notification_text:
                            await message.edit(content=notification_text, embed=embed, view=view)
                        else:
                            await message.edit(embed=embed, view=view)
                        logger.info(f"Twitch: Сообщение о стриме {channel} обновлено")
                        return
                except Exception as e:
                    logger.error(f"Twitch: Ошибка при обновлении сообщения: {e}")
                    del self.stream_messages[channel]
                    self.save_state()

            # Если сообщения нет или не удалось его обновить, создаем новое
            self.stream_categories[channel] = stream_data['game_name']
            embed = Embed(
                title=f"🎮 {stream_data['title']}",
                description=f"{description}\n\n**Категория:** {stream_data['game_name']}",
                color=0x9146FF
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            view = ui.View()
            button = ui.Button(label="Перейти на канал", url=f"https://twitch.tv/{channel}", style=ButtonStyle.url)
            view.add_item(button)
            
            # Отправляем уведомление и сохраняем ID сообщения
            if notification_text:
                message = await notification_channel.send(content=notification_text, embed=embed, view=view)
            else:
                message = await notification_channel.send(embed=embed, view=view)
            self.stream_messages[channel] = message.id
            self.save_state()
        except Exception as e:
            logger.error(f"Twitch: Ошибка при обработке начала стрима: {e}")

    async def on_stream_end(self, channel, description):
        """Действия при окончании стрима"""
        try:
            # Получаем канал для уведомлений
            notification_channel = self.bot.get_channel(TWITCH_NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                logger.info("Twitch: Канал для уведомлений не найден")
                return

            # Загружаем данные стримера для получения текста уведомления
            streamers = self.load_streamers()
            streamer_data = streamers.get(channel, {})
            notification_text = streamer_data.get("notification_text", "")

            # Получаем ID сообщения о стриме
            message_id = self.stream_messages.get(channel)
            if message_id:
                try:
                    # Получаем сообщение
                    message = await notification_channel.fetch_message(message_id)
                    if message:
                        # Редактируем сообщение
                        embed = message.embeds[0]
                        embed.description = f"{description}\n\n**Стрим закончился!**"
                        embed.color = 0x808080  # Серый цвет для завершенного стрима
                        
                        # Убираем текст уведомления при окончании стрима
                        await message.edit(content=None, embed=embed)
                        # Только запускаем задачу на удаление!
                        delete_task = self.bot.loop.create_task(self.delete_message_after_delay(message, channel))
                        self.pending_deletions[channel] = delete_task
                except Exception as e:
                    logger.error(f"Twitch: Ошибка при редактировании сообщения: {e}")
                    # Если не удалось редактировать сообщение, удаляем его из словаря
                    del self.stream_messages[channel]
                    self.save_state()
        except Exception as e:
            logger.error(f"Twitch: Ошибка при обработке окончания стрима: {e}")

    async def delete_message_after_delay(self, message, channel):
        """Удаление сообщения через 5 минут"""
        await asyncio.sleep(300)
        if channel in self.streaming and self.streaming[channel]:
            logger.info(f"Twitch: Стрим {channel} возобновился, сообщение не будет удалено")
            return
        try:
            await message.delete()
            logger.info(f"Twitch: Сообщение о стриме {channel} удалено")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при удалении сообщения: {e}")
        # Только теперь удаляем из словарей и сохраняем состояние!
        if channel in self.stream_messages:
            del self.stream_messages[channel]
        if channel in self.stream_categories:
            del self.stream_categories[channel]
        self.save_state()
        if channel in self.pending_deletions:
            del self.pending_deletions[channel]

    async def twitch_check_loop(self):
        """Цикл проверки статуса стрима"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                logger.debug(f"Twitch: Начинаем проверку стримов, интервал: {TWITCH_CHECK_INTERVAL}")
                await self.check_stream_status()
                logger.debug(f"Twitch: Проверка завершена, ожидаем {TWITCH_CHECK_INTERVAL} секунд")
                await asyncio.sleep(TWITCH_CHECK_INTERVAL)  # Интервал проверки в секундах
            except Exception as e:
                logger.error(f"Twitch: Ошибка в цикле проверки: {e}")
                import traceback
                logger.error(f"Twitch: Полный стек ошибки в цикле: {traceback.format_exc()}")
                await asyncio.sleep(60)  # При ошибке ждем минуту перед следующей попыткой

    async def update_stream_category(self, channel, stream_data):
        """Обновление категории в сообщении о стриме"""
        try:
            # Получаем канал для уведомлений
            notification_channel = self.bot.get_channel(TWITCH_NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                logger.error("Twitch: Канал для уведомлений не найден")
                return

            # Загружаем данные стримера для получения текста уведомления
            streamers = self.load_streamers()
            streamer_data = streamers.get(channel, {})
            notification_text = streamer_data.get("notification_text", "")

            # Получаем ID сообщения о стриме
            message_id = self.stream_messages.get(channel)
            if message_id:
                try:
                    # Получаем сообщение
                    message = await notification_channel.fetch_message(message_id)
                    if message:
                        # Обновляем категорию в словаре
                        self.stream_categories[channel] = stream_data['game_name']
                        
                        # Редактируем сообщение
                        embed = message.embeds[0]
                        embed.description = embed.description.replace(
                            f"**Категория:** {embed.description.split('**Категория:**')[1].split('**Зрителей:**')[0].strip()}",
                            f"**Категория:** {stream_data['game_name']}"
                        )
                        
                        # Отправляем текст уведомления отдельно, если он есть
                        if notification_text:
                            await message.edit(content=notification_text, embed=embed)
                        else:
                            await message.edit(embed=embed)
                except Exception as e:
                    logger.error(f"Twitch: Ошибка при обновлении категории: {e}")
        except Exception as e:
            logger.error(f"Twitch: Ошибка при обновлении категории: {e}")

    def cog_unload(self):
        """Остановка задачи при выгрузке кога"""
        if self.task:
            self.task.cancel()
        # Отменяем все задачи на удаление
        for task in self.pending_deletions.values():
            task.cancel()
        # Сохраняем состояние перед выгрузкой
        self.save_state()

    def load_avatar_cache(self):
        path = "data/avatar_cache.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.avatar_cache = json.load(f)
            except Exception as e:
                logger.error(f"Twitch: Ошибка при загрузке кэша аватарок: {e}")

    def save_avatar_cache(self):
        path = "data/avatar_cache.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.avatar_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Twitch: Ошибка при сохранении кэша аватарок: {e}")

def setup(bot: Bot):
    bot.add_cog(TwitchStream(bot)) 