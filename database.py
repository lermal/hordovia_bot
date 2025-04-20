import aiosqlite
from pathlib import Path
from typing import Optional, Tuple

class Database:
    def __init__(self):
        self.db_path = Path("bot_data.db")
        self.conn: Optional[aiosqlite.Connection] = None

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
            """
        )
        await self.conn.commit()

    async def get_guild_channels(self, guild_id: int) -> Optional[Tuple[int, int]]:
        await self.connect()  # Добавляем подключение
        async with self.conn.execute(
            "SELECT channel_id, category_id FROM channels WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def update_channel(self, guild_id: int, channel_id: int, category_id: int) -> None:
        await self.connect()  # Гарантируем соединение
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

    async def get_private_room(self, owner_id: int) -> Optional[Tuple]:
        """Получение данных приватной комнаты"""
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
        await self.conn.execute(
            "INSERT OR REPLACE INTO privates VALUES (?, ?, ?, ?, ?)",
            data
        )
        await self.conn.commit()

    async def delete_private_room(self, voice_id: int) -> None:
        """Удаление приватной комнаты"""
        await self.conn.execute(
            "DELETE FROM privates WHERE voiceid = ?",
            (voice_id,)
        )
        await self.conn.commit()

    async def transfer_rights(self, new_owner_id: int, private_voice_id: int) -> None:
        """Передача прав на приватную комнату"""
        # Сначала получаем текущие данные о комнате
        async with self.conn.execute(
            "SELECT * FROM privates WHERE voiceid = ?", 
            (private_voice_id,)
        ) as cursor:
            room_data = await cursor.fetchone()
        
        if room_data:
            # Обновляем запись с новым владельцем
            await self.conn.execute(
                "UPDATE privates SET ownerid = ?, perms = ? WHERE voiceid = ?",
                (new_owner_id, new_owner_id, private_voice_id)
            )
            await self.conn.commit()
            return True
        return False

    async def delete_private_room_by_owner(self, owner_id: int) -> None:
        """Удаление приватной комнаты по ID владельца"""
        await self.conn.execute(
            "DELETE FROM privates WHERE ownerid = ? AND ownerid != perms",
            (owner_id,)
        )
        await self.conn.commit()