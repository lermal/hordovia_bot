import aiosqlite
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import asyncio
import time
from functools import lru_cache

class Database:
    def __init__(self):
        self.db_path = Path("./data/database.db")
        self.conn: Optional[aiosqlite.Connection] = None
        self._guild_cache: Dict[int, Tuple[int, int]] = {}
        self._cache_lock = asyncio.Lock()
        self._last_cache_update = 0
        self._cache_ttl = 300  # 5 минут

    async def connect(self) -> None:
        """Установка соединения с БД"""
        if not self.conn:
            self.conn = await aiosqlite.connect(self.db_path)
            await self._init_db()

    async def _init_db(self) -> None:
        """Инициализация таблиц"""
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS privates (
                ownerid BIGINT PRIMARY KEY,
                voicename TEXT,
                voicelim INTEGER,
                voiceid BIGINT,
                perms BIGINT
            );
            
            CREATE TABLE IF NOT EXISTS role_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                UNIQUE(message_id, emoji)
            );
            
            -- Индексы для оптимизации поиска
            CREATE INDEX IF NOT EXISTS idx_privates_voiceid ON privates(voiceid);
            CREATE INDEX IF NOT EXISTS idx_privates_ownerid ON privates(ownerid);
            CREATE INDEX IF NOT EXISTS idx_channels_guild_id ON channels(guild_id);
            CREATE INDEX IF NOT EXISTS idx_role_reactions_message_id ON role_reactions(message_id);
            CREATE INDEX IF NOT EXISTS idx_role_reactions_guild_id ON role_reactions(guild_id);
            """
        )
        
        await self.conn.commit()

    async def get_guild_channels(self, guild_id: int) -> Optional[Tuple[int, int]]:
        """Получение данных каналов гильдии с кэшированием"""
        # Проверяем кэш
        async with self._cache_lock:
            current_time = time.time()
            if (current_time - self._last_cache_update < self._cache_ttl and 
                guild_id in self._guild_cache):
                return self._guild_cache[guild_id]
        
        await self.connect()
        async with self.conn.execute(
            "SELECT channel_id, category_id FROM channels WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            result = await cursor.fetchone()
            
            # Обновляем кэш
            async with self._cache_lock:
                if result:
                    self._guild_cache[guild_id] = result
                self._last_cache_update = current_time
            
            return result

    async def update_channel(self, guild_id: int, channel_id: int, category_id: int) -> None:
        await self.connect()
        await self.conn.execute(
            "INSERT OR REPLACE INTO channels VALUES (?, ?, ?)",
            (guild_id, channel_id, category_id)
        )
        await self.conn.commit()

    async def delete_guild_channels(self, guild_id: int) -> None:
        """Удаление данных гильдии (для будущего сброса)"""
        await self.connect()
        await self.conn.execute(
            "DELETE FROM channels WHERE guild_id = ?",
            (guild_id,)
        )
        await self.conn.commit()

    async def save_guild_channels(self, data: Tuple[int, int, int]) -> None:
        """Сохранение данных каналов гильдии"""
        await self.connect()
        await self.conn.execute(
            "INSERT OR REPLACE INTO channels VALUES (?, ?, ?)",
            data
        )
        await self.conn.commit()
        
        # Обновляем кэш
        async with self._cache_lock:
            self._guild_cache[data[0]] = (data[1], data[2])
            self._last_cache_update = time.time()

    async def invalidate_guild_cache(self, guild_id: int = None) -> None:
        """Инвалидация кэша гильдии"""
        async with self._cache_lock:
            if guild_id:
                self._guild_cache.pop(guild_id, None)
            else:
                self._guild_cache.clear()
            self._last_cache_update = 0

    async def get_private_room(self, owner_id: int) -> Optional[Tuple]:
        """Получение данных приватной комнаты"""
        await self.connect()
        async with self.conn.execute(
            "SELECT * FROM privates WHERE ownerid = ?", 
            (owner_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def get_private_room_by_channel(self, voice_id: int) -> Optional[Tuple]:
        """Получение данных приватной комнаты по ID канала"""
        await self.connect()
        async with self.conn.execute(
            "SELECT * FROM privates WHERE voiceid = ?", 
            (voice_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def update_private_room(self, data: Tuple) -> None:
        """Обновление данных приватной комнаты"""
        await self.connect()
        await self.conn.execute(
            "INSERT OR REPLACE INTO privates VALUES (?, ?, ?, ?, ?)",
            data
        )
        await self.conn.commit()

    async def delete_private_room(self, voice_id: int) -> None:
        """Удаление приватной комнаты"""
        await self.connect()
        await self.conn.execute(
            "DELETE FROM privates WHERE voiceid = ?",
            (voice_id,)
        )
        await self.conn.commit()

    async def transfer_rights(self, new_owner_id: int, private_voice_id: int) -> None:
        """Передача прав на приватную комнату"""
        await self.connect()
        async with self.conn.execute(
            "SELECT * FROM privates WHERE voiceid = ?", 
            (private_voice_id,)
        ) as cursor:
            room_data = await cursor.fetchone()
        
        if room_data:
            await self.conn.execute(
                "UPDATE privates SET ownerid = ?, perms = ? WHERE voiceid = ?",
                (new_owner_id, new_owner_id, private_voice_id)
            )
            await self.conn.commit()
            return True
        return False

    async def delete_private_room_by_owner(self, owner_id: int) -> None:
        """Удаление приватной комнаты по ID владельца"""
        await self.connect()
        await self.conn.execute(
            "DELETE FROM privates WHERE ownerid = ? AND ownerid != perms",
            (owner_id,)
        )
        await self.conn.commit()
        
    # Методы для работы с ролевыми реакциями
    async def add_role_reaction(self, guild_id: int, channel_id: int, message_id: int, emoji: str, role_id: int):
        """Добавляет новую ролевую реакцию"""
        await self.connect()
        try:
            await self.conn.execute(
                """
                INSERT INTO role_reactions 
                (guild_id, channel_id, message_id, emoji, role_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, message_id, emoji, role_id)
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            # Если такая комбинация message_id и emoji уже существует
            return False

    async def remove_role_reaction(self, message_id: int, emoji: str):
        """Удаляет ролевую реакцию"""
        await self.connect()
        await self.conn.execute(
            """
            DELETE FROM role_reactions 
            WHERE message_id = ? AND emoji = ?
            """,
            (message_id, emoji)
        )
        await self.conn.commit()
        
    async def get_role_reaction(self, message_id: int, emoji: str):
        """Получает информацию о ролевой реакции по сообщению и эмодзи"""
        await self.connect()
        async with self.conn.execute(
            """
            SELECT * FROM role_reactions 
            WHERE message_id = ? AND emoji = ?
            """,
            (message_id, emoji)
        ) as cursor:
            return await cursor.fetchone()
            
    async def get_all_role_reactions(self):
        """Получает все ролевые реакции"""
        await self.connect()
        async with self.conn.execute("SELECT * FROM role_reactions") as cursor:
            return [row async for row in cursor]
            
    async def get_message_role_reactions(self, message_id: int):
        """Получает все ролевые реакции для конкретного сообщения"""
        await self.connect()
        async with self.conn.execute(
            """
            SELECT * FROM role_reactions 
            WHERE message_id = ?
            """,
            (message_id,)
        ) as cursor:
            return [row async for row in cursor]
            
    async def remove_message_reactions(self, message_id: int):
        """Удаляет все ролевые реакции для конкретного сообщения"""
        await self.connect()
        await self.conn.execute(
            """
            DELETE FROM role_reactions 
            WHERE message_id = ?
            """,
            (message_id,)
        )
        await self.conn.commit()
        
    async def update_role_reaction(self, message_id: int, emoji: str, new_role_id: int):
        """Обновляет роль для указанной реакции"""
        await self.connect()
        await self.conn.execute(
            """
            UPDATE role_reactions 
            SET role_id = ? 
            WHERE message_id = ? AND emoji = ?
            """,
            (new_role_id, message_id, emoji)
        )
        await self.conn.commit()

    async def get_all_private_rooms(self) -> list:
        """Получение всех приватных комнат"""
        await self.connect()
        async with self.conn.execute("SELECT * FROM privates") as cursor:
            return await cursor.fetchall()

    # Оптимизированные методы для работы с транзакциями
    async def batch_delete_private_rooms(self, voice_ids: list) -> None:
        """Пакетное удаление приватных комнат"""
        await self.connect()
        if not voice_ids:
            return
        
        placeholders = ','.join('?' * len(voice_ids))
        await self.conn.execute(
            f"DELETE FROM privates WHERE voiceid IN ({placeholders})",
            voice_ids
        )
        await self.conn.commit()

    async def batch_update_private_rooms(self, rooms_data: list) -> None:
        """Пакетное обновление приватных комнат"""
        await self.connect()
        if not rooms_data:
            return
        
        await self.conn.executemany(
            "INSERT OR REPLACE INTO privates VALUES (?, ?, ?, ?, ?)",
            rooms_data
        )
        await self.conn.commit()

    async def get_private_rooms_by_owners(self, owner_ids: list) -> dict:
        """Получение приватных комнат для нескольких владельцев"""
        await self.connect()
        if not owner_ids:
            return {}
        
        placeholders = ','.join('?' * len(owner_ids))
        async with self.conn.execute(
            f"SELECT * FROM privates WHERE ownerid IN ({placeholders})",
            owner_ids
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row for row in rows}  # ownerid: room_data

    async def cleanup_empty_rooms(self) -> list:
        """Очистка пустых комнат - возвращает список ID комнат для удаления"""
        await self.connect()
        async with self.conn.execute("SELECT voiceid FROM privates") as cursor:
            voice_ids = [row[0] async for row in cursor]
        
        rooms_to_delete = []
        for voice_id in voice_ids:
            channel = self.bot.get_channel(voice_id) if hasattr(self, 'bot') else None
            if not channel or (isinstance(channel, nextcord.VoiceChannel) and len(channel.members) == 0):
                rooms_to_delete.append(voice_id)
        
        if rooms_to_delete:
            await self.batch_delete_private_rooms(rooms_to_delete)
        
        return rooms_to_delete