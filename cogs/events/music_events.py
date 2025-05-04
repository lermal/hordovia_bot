import nextcord
from nextcord.ext import commands, tasks
import asyncio

class MusicEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_voice_channels.start()
    
    def cog_unload(self):
        """Вызывается при выгрузке кога"""
        self.check_voice_channels.cancel()
        
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Обработчик изменения состояния голосового канала"""
        # Если бот не инициализирован, выходим
        if not hasattr(self.bot, "music_bot_pool"):
            return
            
        # Если бот вышел из голосового канала, очищаем музыкальные ресурсы
        if member.id == self.bot.user.id and before.channel and not after.channel:
            if before.channel.id in self.bot.music_bot_pool.channel_bot_mapping:
                await self.bot.music_bot_pool.release_bot(before.channel.id)
        
        # Если пользователь вышел из голосового канала, проверяем, остался ли бот один
        if before.channel and member.id != self.bot.user.id:
            # Получаем голосовой клиент для канала, из которого вышел пользователь
            voice_client = nextcord.utils.get(self.bot.voice_clients, channel=before.channel)
            if voice_client:
                # Если в канале не осталось пользователей (кроме ботов), отключаемся через 2 минуты
                members = [m for m in before.channel.members if not m.bot]
                if not members:
                    # Ждем 2 минуты
                    await asyncio.sleep(120)
                    
                    # Проверяем снова, может кто-то уже подключился
                    current_channel = voice_client.channel
                    if current_channel:
                        members = [m for m in current_channel.members if not m.bot]
                        if not members:
                            # Если всё ещё никто не подключился, отключаемся
                            await voice_client.disconnect()
                            
                            # Освобождаем бота
                            if current_channel.id in self.bot.music_bot_pool.channel_bot_mapping:
                                await self.bot.music_bot_pool.release_bot(current_channel.id)
    
    @commands.command()
    @commands.is_owner()
    async def cleanup_music(self, ctx):
        """Очищает все музыкальные ресурсы и отключает ботов от всех каналов"""
        if not hasattr(self.bot, "music_bot_pool"):
            return await ctx.send("Музыкальный пул не инициализирован")
            
        await ctx.send("Начинаю очистку музыкальных ресурсов...")
        
        # Отключаем всех музыкальных ботов
        await self.bot.music_bot_pool.cleanup_all()
        
        # Отключаем голосовые клиенты основного бота
        for voice_client in self.bot.voice_clients:
            await voice_client.disconnect()
            
        await ctx.send("Очистка музыкальных ресурсов завершена")
    
    @tasks.loop(minutes=5)
    async def check_voice_channels(self):
        """Проверяет все голосовые каналы и отключается от пустых"""
        # Пропускаем, если бот не инициализирован
        if not self.bot.initialised or not hasattr(self.bot, "music_bot_pool"):
            return
            
        for voice_client in self.bot.voice_clients:
            # Проверяем, есть ли в канале пользователи (не боты)
            members = [m for m in voice_client.channel.members if not m.bot]
            if not members:
                # Отключаемся от пустого канала
                await voice_client.disconnect()
                
                # Освобождаем бота
                if voice_client.channel.id in self.bot.music_bot_pool.channel_bot_mapping:
                    await self.bot.music_bot_pool.release_bot(voice_client.channel.id)
    
    @check_voice_channels.before_loop
    async def before_check_voice_channels(self):
        """Ждем, пока бот будет готов, прежде чем начать проверку каналов"""
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Обработчик готовности бота"""
        # Инициализируем музыкальный пул, если он еще не инициализирован
        if not hasattr(self.bot, "music_bot_pool"):
            from utils.music_bot_pool import MusicBotPool
            self.bot.music_bot_pool = MusicBotPool(self.bot)

def setup(bot):
    bot.add_cog(MusicEvents(bot)) 