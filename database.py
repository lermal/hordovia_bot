import aiosqlite
from pathlib import Path

class Database:
    def __init__(self):
        self.db_path = Path("bot_data.db")
        self.conn = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self._init_db()
        return self

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def _init_db(self):
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL
            )
            """
        )
        await self.conn.commit()

    async def load_all_channels(self):
        async with self.conn.execute("SELECT * FROM channels") as cursor:
            return {row[0]: (row[1], row[2]) async for row in cursor}

    async def set_channel(self, guild_id: int, channel_id: int, category_id: int):
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO channels 
            (guild_id, channel_id, category_id)
            VALUES (?, ?, ?)
            """,
            (guild_id, channel_id, category_id)
        )
        await self.conn.commit()