from config import *
from bot import Bot
from nextcord import RawReactionActionEvent
from nextcord.ext.commands import Cog
import asyncio

class RoleReactionEvents(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.cache = {}  # {message_id: {emoji: role_id}}
        self.bot.loop.create_task(self.load_reactions())
        
    async def load_reactions(self):
        """Загружает все реакции в кэш"""
        await self.bot.wait_until_ready()
        
        # Ждем, пока база данных будет инициализирована
        while not self.bot.db.conn:
            await asyncio.sleep(1)
            print("Ожидание инициализации БД в RoleReactionEvents...")
            
        try:
            reactions = await self.bot.db.get_all_role_reactions()
            
            for reaction in reactions:
                message_id = reaction[3]
                emoji = reaction[4]
                role_id = reaction[5]
                
                if message_id not in self.cache:
                    self.cache[message_id] = {}
                    
                self.cache[message_id][emoji] = role_id
                
            print(f"Загружено {len(reactions)} ролевых реакций")
        except Exception as e:
            print(f"Ошибка при загрузке ролевых реакций: {e}")
    
    @Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        # Игнорируем реакции от ботов
        if payload.member and payload.member.bot:
            return
            
        # Проверяем, есть ли реакция в кэше
        message_id = payload.message_id
        emoji = str(payload.emoji)
        
        if message_id in self.cache and emoji in self.cache[message_id]:
            role_id = self.cache[message_id][emoji]
            
            # Получаем роль и выдаем её пользователю
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
                
            role = guild.get_role(role_id)
            if not role:
                return
                
            member = payload.member
            if not member:
                # Если по какой-то причине member не получен через payload, пробуем получить через guild
                member = guild.get_member(payload.user_id)
                
            if not member:
                return
                
            try:
                await member.add_roles(role, reason="Роль по реакции")
            except Exception as e:
                print(f"Ошибка при выдаче роли: {e}")
    
    @Cog.listener("on_raw_reaction_remove")
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        # Проверяем, есть ли реакция в кэше
        message_id = payload.message_id
        emoji = str(payload.emoji)
        
        if message_id in self.cache and emoji in self.cache[message_id]:
            role_id = self.cache[message_id][emoji]
            
            # Получаем роль и забираем её у пользователя
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
                
            role = guild.get_role(role_id)
            if not role:
                return
                
            # В случае on_raw_reaction_remove у нас нет payload.member, поэтому получаем через guild
            member = guild.get_member(payload.user_id)
            if not member:
                return
                
            try:
                await member.remove_roles(role, reason="Роль по реакции")
            except Exception as e:
                print(f"Ошибка при удалении роли: {e}")
    
    @Cog.listener("on_raw_reaction_clear")
    async def on_raw_reaction_clear(self, payload):
        """Обрабатывает событие очистки всех реакций с сообщения"""
        message_id = payload.message_id
        
        # Проверяем, есть ли это сообщение в нашем кэше
        if message_id in self.cache:
            print(f"Обнаружена очистка реакций для сообщения {message_id}, которое есть в кэше роль-реакций")
            
            # Получаем информацию о сообщении
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
                
            channel = guild.get_channel(payload.channel_id)
            if not channel:
                return
            
            # Получаем сообщение
            try:
                message = await channel.fetch_message(message_id)
            except Exception as e:
                print(f"Не удалось получить сообщение {message_id}: {e}")
                return
            
            # Ждем немного времени перед восстановлением реакций (5 секунд)
            await asyncio.sleep(5)
            
            # Восстанавливаем все реакции из кэша
            reactions_restored = 0
            for emoji, role_id in self.cache[message_id].items():
                try:
                    await message.add_reaction(emoji)
                    reactions_restored += 1
                    # Небольшая задержка между добавлением реакций, чтобы избежать рейт-лимитов Discord
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Ошибка при восстановлении реакции {emoji} для сообщения {message_id}: {e}")
            
            print(f"Восстановлено {reactions_restored} реакций для сообщения {message_id}")

    @Cog.listener("on_raw_reaction_clear_emoji")
    async def on_raw_reaction_clear_emoji(self, payload):
        """Обрабатывает событие очистки конкретной реакции с сообщения"""
        message_id = payload.message_id
        emoji = str(payload.emoji)
        
        # Проверяем, есть ли эта реакция в нашем кэше
        if message_id in self.cache and emoji in self.cache[message_id]:
            print(f"Обнаружена очистка реакции {emoji} для сообщения {message_id}, которая есть в кэше роль-реакций")
            
            # Получаем информацию о сообщении
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
                
            channel = guild.get_channel(payload.channel_id)
            if not channel:
                return
            
            # Получаем сообщение
            try:
                message = await channel.fetch_message(message_id)
            except Exception as e:
                print(f"Не удалось получить сообщение {message_id}: {e}")
                return
            
            # Ждем немного времени перед восстановлением реакции (3 секунды)
            await asyncio.sleep(3)
            
            # Восстанавливаем реакцию
            try:
                await message.add_reaction(emoji)
                print(f"Восстановлена реакция {emoji} для сообщения {message_id}")
            except Exception as e:
                print(f"Ошибка при восстановлении реакции {emoji} для сообщения {message_id}: {e}")
    
    async def update_cache(self, message_id, emoji, role_id=None):
        """Обновляет кэш реакций"""
        if message_id not in self.cache:
            self.cache[message_id] = {}
            
        if role_id is None:
            # Если role_id не указан, удаляем из кэша
            if emoji in self.cache[message_id]:
                del self.cache[message_id][emoji]
                
            # Если у сообщения не осталось реакций, удаляем его из кэша
            if not self.cache[message_id]:
                del self.cache[message_id]
        else:
            # Добавляем или обновляем реакцию в кэше
            self.cache[message_id][emoji] = role_id

def setup(bot: Bot):
    bot.add_cog(RoleReactionEvents(bot)) 