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
        
        # Создаем таблицу для ролевых реакций
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                UNIQUE(message_id, emoji)
            )
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

    # Методы для работы с ролевыми реакциями
    async def add_role_reaction(self, guild_id: int, channel_id: int, message_id: int, emoji: str, role_id: int):
        """Добавляет новую ролевую реакцию"""
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
        async with self.conn.execute("SELECT * FROM role_reactions") as cursor:
            return [row async for row in cursor]
            
    async def get_message_role_reactions(self, message_id: int):
        """Получает все ролевые реакции для конкретного сообщения"""
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
        await self.conn.execute(
            """
            UPDATE role_reactions 
            SET role_id = ? 
            WHERE message_id = ? AND emoji = ?
            """,
            (new_role_id, message_id, emoji)
        )
        await self.conn.commit()