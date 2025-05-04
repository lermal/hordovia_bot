import asyncio
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import nextcord
from nextcord.ext.commands import Bot
from utils.music_manager import MusicManager, Track

@dataclass
class MusicBotConfig:
    token: str
    bot_id: int
    status: str = "ready"  # ready, busy, offline


class MusicBotPool:
    """Управляет пулом ботов-партнеров для распределения музыкальной нагрузки"""
    
    def __init__(self, main_bot):
        self.main_bot = main_bot
        self.bot_configs: Dict[int, MusicBotConfig] = {}  # {bot_id: config}
        self.active_bots: Dict[int, Bot] = {}  # {bot_id: bot_instance}
        self.channel_bot_mapping: Dict[int, int] = {}  # {channel_id: bot_id}
        self.manager_instances: Dict[int, MusicManager] = {}  # {bot_id: MusicManager}
        
        # Загружаем конфиги ботов
        self._load_bot_configs()
    
    def _load_bot_configs(self):
        """Загружает конфигурации ботов из файла"""
        config_path = os.path.join("data", "music_bots.json")
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                
                for bot_id, config in configs.items():
                    self.bot_configs[int(bot_id)] = MusicBotConfig(
                        token=config["token"],
                        bot_id=int(bot_id),
                        status=config.get("status", "ready")
                    )
            except Exception as e:
                print(f"Ошибка при загрузке конфигураций ботов: {e}")
        else:
            # Создаем пустой файл конфигурации
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({}, f)
    
    def _save_bot_configs(self):
        """Сохраняет конфигурации ботов в файл"""
        config_path = os.path.join("data", "music_bots.json")
        
        configs = {}
        for bot_id, config in self.bot_configs.items():
            configs[str(bot_id)] = {
                "token": config.token,
                "status": config.status
            }
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=4)
    
    async def add_bot(self, token: str) -> Tuple[bool, str]:
        """Добавляет нового бота в пул"""
        # Создаем временного бота для получения его ID
        temp_bot = Bot(command_prefix="!")
        
        try:
            # Начинаем процесс входа для получения ID
            await temp_bot.login(token)
            bot_id = temp_bot.user.id
            
            # Сразу выходим, так как нам нужен только ID
            await temp_bot.close()
            
            # Проверяем, есть ли уже бот с таким ID
            if bot_id in self.bot_configs:
                return False, "Бот с таким ID уже существует в пуле"
            
            # Добавляем бота в конфигурацию
            self.bot_configs[bot_id] = MusicBotConfig(
                token=token,
                bot_id=bot_id
            )
            
            # Сохраняем конфигурацию
            self._save_bot_configs()
            
            return True, f"Бот с ID {bot_id} успешно добавлен в пул"
        except Exception as e:
            await temp_bot.close()
            return False, f"Ошибка при добавлении бота: {str(e)}"
    
    async def remove_bot(self, bot_id: int) -> bool:
        """Удаляет бота из пула"""
        if bot_id not in self.bot_configs:
            return False
        
        # Если бот активен, останавливаем его
        if bot_id in self.active_bots:
            await self.stop_bot(bot_id)
        
        # Удаляем бота из конфигурации
        del self.bot_configs[bot_id]
        
        # Удаляем отображения каналов на этого бота
        for channel_id, mapped_bot_id in list(self.channel_bot_mapping.items()):
            if mapped_bot_id == bot_id:
                del self.channel_bot_mapping[channel_id]
        
        # Сохраняем конфигурацию
        self._save_bot_configs()
        
        return True
    
    async def start_bot(self, bot_id: int) -> bool:
        """Запускает бота"""
        if bot_id not in self.bot_configs or bot_id in self.active_bots:
            return False
        
        config = self.bot_configs[bot_id]
        
        # Создаем инстанс бота
        bot = Bot(command_prefix="!", intents=nextcord.Intents.all())
        
        try:
            # Создаем менеджер музыки для этого бота
            music_manager = MusicManager(bot)
            self.manager_instances[bot_id] = music_manager
            
            # Добавляем обработчик события ready
            @bot.event
            async def on_ready():
                print(f"Музыкальный бот {bot.user.name} ({bot.user.id}) запущен")
                config.status = "ready"
                
                # Синхронизация команд
                try:
                    print(f"Синхронизация слеш-команд...")
                    synced = await bot.sync_commands()
                    print(f"Синхронизировано {len(synced)} команд")
                except Exception as e:
                    print(f"Ошибка при синхронизации команд: {e}")
            
            # Запускаем бота в отдельной задаче
            self.active_bots[bot_id] = bot
            asyncio.create_task(bot.start(config.token))
            
            return True
        except Exception as e:
            print(f"Ошибка при запуске бота {bot_id}: {e}")
            return False
    
    async def stop_bot(self, bot_id: int) -> bool:
        """Останавливает бота"""
        if bot_id not in self.active_bots:
            return False
        
        bot = self.active_bots[bot_id]
        
        # Очищаем ресурсы музыкального менеджера
        if bot_id in self.manager_instances:
            await self.manager_instances[bot_id].cleanup()
            del self.manager_instances[bot_id]
        
        # Останавливаем бота
        await bot.close()
        
        # Удаляем из активных ботов
        del self.active_bots[bot_id]
        
        # Обновляем статус
        if bot_id in self.bot_configs:
            self.bot_configs[bot_id].status = "offline"
        
        return True
    
    def get_available_bot(self) -> Optional[int]:
        """Возвращает ID доступного бота"""
        for bot_id, config in self.bot_configs.items():
            if config.status == "ready" and bot_id in self.active_bots:
                return bot_id
        
        # Если нет готовых ботов, возвращаем первого оффлайн-бота для запуска
        for bot_id, config in self.bot_configs.items():
            if config.status == "offline":
                return bot_id
        
        return None
    
    async def get_bot_for_channel(self, channel_id: int) -> Optional[int]:
        """Получает или назначает бота для голосового канала"""
        # Проверяем, есть ли уже назначенный бот для этого канала
        if channel_id in self.channel_bot_mapping:
            bot_id = self.channel_bot_mapping[channel_id]
            
            # Проверяем, активен ли этот бот
            if bot_id in self.active_bots:
                return bot_id
            
            # Если бот не активен, удаляем маппинг и ищем нового
            del self.channel_bot_mapping[channel_id]
        
        # Получаем доступного бота
        bot_id = self.get_available_bot()
        if not bot_id:
            return None
        
        # Если бот оффлайн, запускаем его
        if bot_id in self.bot_configs and self.bot_configs[bot_id].status == "offline":
            success = await self.start_bot(bot_id)
            if not success:
                return None
        
        # Назначаем бот каналу
        self.channel_bot_mapping[channel_id] = bot_id
        
        # Обновляем статус бота
        if bot_id in self.bot_configs:
            self.bot_configs[bot_id].status = "busy"
        
        return bot_id
    
    async def release_bot(self, channel_id: int) -> bool:
        """Освобождает бота после использования"""
        if channel_id not in self.channel_bot_mapping:
            return False
        
        bot_id = self.channel_bot_mapping[channel_id]
        
        # Удаляем маппинг
        del self.channel_bot_mapping[channel_id]
        
        # Проверяем, используется ли бот другими каналами
        is_used = False
        for _, mapped_bot_id in self.channel_bot_mapping.items():
            if mapped_bot_id == bot_id:
                is_used = True
                break
        
        # Если бот больше не используется, обновляем его статус
        if not is_used and bot_id in self.bot_configs:
            self.bot_configs[bot_id].status = "ready"
        
        return True
    
    def get_music_manager(self, bot_id: int) -> Optional[MusicManager]:
        """Получает менеджер музыки для конкретного бота"""
        return self.manager_instances.get(bot_id)
    
    async def add_track_to_channel(self, channel_id: int, query: str) -> Optional[Track]:
        """Добавляет трек в очередь для конкретного канала"""
        # Получаем или назначаем бота для канала
        bot_id = await self.get_bot_for_channel(channel_id)
        if not bot_id:
            return None
        
        # Получаем менеджер музыки
        music_manager = self.get_music_manager(bot_id)
        if not music_manager:
            return None
        
        # Добавляем трек
        return await music_manager.add_track(channel_id, query)
    
    async def cleanup_all(self):
        """Останавливает всех активных ботов"""
        for bot_id in list(self.active_bots.keys()):
            await self.stop_bot(bot_id)
        
        self.channel_bot_mapping.clear() 