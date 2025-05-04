import nextcord
from nextcord import SlashOption, Interaction, slash_command
from nextcord.ext import commands
from views.music_menu import MusicMenuView
from utils.music_manager import MusicManager
from utils.music_bot_pool import MusicBotPool

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.logger.info("Инициализация музыкального модуля...")
        
        # Инициализируем пул ботов, если он еще не инициализирован
        if not hasattr(bot, "music_bot_pool"):
            bot.music_bot_pool = MusicBotPool(bot)
            self.bot.logger.info("Создан новый пул музыкальных ботов")
        else:
            self.bot.logger.info("Использован существующий пул музыкальных ботов")
        self.music_bot_pool = bot.music_bot_pool
        
        # Инициализируем MusicManager для основного бота
        self.music_manager = MusicManager(bot)
        self.bot.logger.info("Музыкальный модуль инициализирован успешно")

    @slash_command(
        name="music", 
        description="Открывает музыкальное меню для воспроизведения музыки"
    )
    async def music(self, interaction: Interaction):
        self.bot.logger.info(f"Вызвана команда /music пользователем {interaction.user.name}")
        # Проверяем, находится ли пользователь в голосовом канале
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "Вы должны находиться в голосовом канале для использования этой команды!", 
                ephemeral=True
            )

        voice_channel = interaction.user.voice.channel
        
        # Отправляем отложенный ответ, пока происходит распределение ботов
        await interaction.response.defer()
        
        # Получаем бота из пула для этого голосового канала
        bot_id = await self.music_bot_pool.get_bot_for_channel(voice_channel.id)
        
        if not bot_id:
            # Если нет доступных ботов в пуле, используем основного бота
            music_manager = self.music_manager
            self.bot.logger.info("Используем основного бота для воспроизведения музыки")
        else:
            # Иначе используем менеджер из пула ботов
            music_manager = self.music_bot_pool.get_music_manager(bot_id)
            if not music_manager:
                music_manager = self.music_manager
            self.bot.logger.info(f"Используем бота {bot_id} для воспроизведения музыки")
        
        try:
            # Создаем объект вида с музыкальным меню
            from views.music_menu import MusicMenuView  # Импортируем здесь, чтобы быть уверенными в использовании свежей версии класса
            view = MusicMenuView(self.bot, interaction.user, voice_channel, music_manager)
            
            # Создаем эмбед для музыкального меню
            embed = nextcord.Embed(
                title="🎵 Музыкальное меню",
                description="Используйте выпадающие списки ниже для управления музыкой.",
                color=nextcord.Color.blurple()
            )
            
            # Добавляем информацию о том, какой бот обслуживает канал
            if bot_id:
                embed.add_field(
                    name="Музыкальный бот", 
                    value=f"ID: {bot_id}", 
                    inline=False
                )
            
            embed.add_field(
                name="Текущий статус", 
                value="⏹️ **Остановлено**", 
                inline=False
            )
            
            embed.add_field(
                name="Текущий трек", 
                value="Ничего не воспроизводится", 
                inline=False
            )
            
            # Добавляем подсказку о поддерживаемых источниках - обновляем, чтобы убрать YouTube
            embed.add_field(
                name="Поддерживаемые источники",
                value="🎧 YouTube (поиск по названию или URL)\n📝 Поисковый запрос (поиск через YouTube Music)", 
                inline=False
            )
            
            embed.set_footer(text=f"Запрошено: {interaction.user.display_name}")
            
            # Отправляем сообщение с интерфейсом
            message = await interaction.followup.send(embed=embed, view=view)
            
            # Устанавливаем ссылку на сообщение в view
            view.message = message
            
            # Сохраняем ссылку на сообщение в MusicBot
            if hasattr(music_manager, 'set_message'):
                music_manager.set_message(voice_channel.id, message)
            
            self.bot.logger.info(f"Музыкальное меню успешно создано для пользователя {interaction.user.name}")
        except Exception as e:
            self.bot.logger.error(f"Ошибка при создании музыкального меню: {e}")
            await interaction.followup.send(
                f"Произошла ошибка при создании музыкального меню: {e}",
                ephemeral=True
            )

    @slash_command(
        name="musictest", 
        description="Тестовая музыкальная команда"
    )
    async def musictest(self, interaction: Interaction):
        self.bot.logger.info(f"Вызвана тестовая команда /musictest пользователем {interaction.user.name}")
        await interaction.response.send_message("Тестовая музыкальная команда работает!", ephemeral=True)

def setup(bot):
    bot.add_cog(Music(bot)) 