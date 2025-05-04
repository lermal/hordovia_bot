import nextcord
from nextcord import SlashOption, Interaction, slash_command
from nextcord.ext import commands
from utils.music_bot_pool import MusicBotPool

class MusicAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Инициализируем пул ботов, если он еще не инициализирован
        if not hasattr(bot, "music_bot_pool"):
            bot.music_bot_pool = MusicBotPool(bot)
        self.music_bot_pool = bot.music_bot_pool

    @slash_command(
        name="musicbot", 
        description="Команды для управления музыкальными ботами",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def musicbot(self, interaction: Interaction):
        """Группа команд для управления музыкальными ботами"""
        pass  # Это базовая команда, которая будет иметь подкоманды

    @musicbot.subcommand(
        name="add",
        description="Добавить нового музыкального бота"
    )
    async def add_bot(
        self, 
        interaction: Interaction, 
        token: str = SlashOption(
            name="token",
            description="Токен бота Discord",
            required=True
        )
    ):
        """Добавляет нового музыкального бота в пул"""
        # Проверяем, является ли пользователь администратором
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "У вас нет прав для использования этой команды!", 
                ephemeral=True
            )

        # Отправляем отложенный ответ, так как операция может занять время
        await interaction.response.defer(ephemeral=True)
        
        # Добавляем бота
        success, message = await self.music_bot_pool.add_bot(token)
        
        await interaction.followup.send(message, ephemeral=True)

    @musicbot.subcommand(
        name="list",
        description="Показать список всех музыкальных ботов"
    )
    async def list_bots(self, interaction: Interaction):
        """Показывает список всех музыкальных ботов"""
        # Проверяем, является ли пользователь администратором
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "У вас нет прав для использования этой команды!", 
                ephemeral=True
            )
        
        # Формируем список ботов
        if not self.music_bot_pool.bot_configs:
            return await interaction.response.send_message(
                "Список музыкальных ботов пуст.", 
                ephemeral=True
            )
        
        embed = nextcord.Embed(
            title="Список музыкальных ботов",
            color=nextcord.Color.blue()
        )
        
        for bot_id, config in self.music_bot_pool.bot_configs.items():
            # Определяем статус бота
            is_active = bot_id in self.music_bot_pool.active_bots
            status_emoji = "🟢" if is_active else "🔴"
            status_text = f"{status_emoji} {config.status.capitalize()}"
            
            # Определяем, какие каналы обслуживает этот бот
            channels = []
            for channel_id, mapped_bot_id in self.music_bot_pool.channel_bot_mapping.items():
                if mapped_bot_id == bot_id:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        channels.append(f"<#{channel_id}>")
            
            channels_text = ", ".join(channels) if channels else "Нет"
            
            # Добавляем поле для бота
            embed.add_field(
                name=f"Бот {bot_id}",
                value=f"Статус: {status_text}\nОбслуживает каналы: {channels_text}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @musicbot.subcommand(
        name="remove",
        description="Удалить музыкального бота из пула"
    )
    async def remove_bot(
        self, 
        interaction: Interaction, 
        bot_id: str = SlashOption(
            name="bot_id",
            description="ID бота для удаления",
            required=True
        )
    ):
        """Удаляет музыкального бота из пула"""
        # Проверяем, является ли пользователь администратором
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "У вас нет прав для использования этой команды!", 
                ephemeral=True
            )
        
        try:
            bot_id = int(bot_id)
        except ValueError:
            return await interaction.response.send_message(
                "Некорректный ID бота. Укажите правильный числовой ID.", 
                ephemeral=True
            )
        
        # Проверяем, существует ли бот с таким ID
        if bot_id not in self.music_bot_pool.bot_configs:
            return await interaction.response.send_message(
                f"Бот с ID {bot_id} не найден в пуле.", 
                ephemeral=True
            )
        
        # Отправляем отложенный ответ
        await interaction.response.defer(ephemeral=True)
        
        # Удаляем бота
        success = await self.music_bot_pool.remove_bot(bot_id)
        
        if success:
            await interaction.followup.send(
                f"Бот с ID {bot_id} успешно удален из пула.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Не удалось удалить бота с ID {bot_id}.", 
                ephemeral=True
            )

    @musicbot.subcommand(
        name="start",
        description="Запустить музыкального бота"
    )
    async def start_bot(
        self, 
        interaction: Interaction, 
        bot_id: str = SlashOption(
            name="bot_id",
            description="ID бота для запуска",
            required=True
        )
    ):
        """Запускает музыкального бота"""
        # Проверяем, является ли пользователь администратором
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "У вас нет прав для использования этой команды!", 
                ephemeral=True
            )
        
        try:
            bot_id = int(bot_id)
        except ValueError:
            return await interaction.response.send_message(
                "Некорректный ID бота. Укажите правильный числовой ID.", 
                ephemeral=True
            )
        
        # Проверяем, существует ли бот с таким ID
        if bot_id not in self.music_bot_pool.bot_configs:
            return await interaction.response.send_message(
                f"Бот с ID {bot_id} не найден в пуле.", 
                ephemeral=True
            )
        
        # Проверяем, не запущен ли уже бот
        if bot_id in self.music_bot_pool.active_bots:
            return await interaction.response.send_message(
                f"Бот с ID {bot_id} уже запущен.", 
                ephemeral=True
            )
        
        # Отправляем отложенный ответ
        await interaction.response.defer(ephemeral=True)
        
        # Запускаем бота
        success = await self.music_bot_pool.start_bot(bot_id)
        
        if success:
            await interaction.followup.send(
                f"Бот с ID {bot_id} успешно запущен.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Не удалось запустить бота с ID {bot_id}.", 
                ephemeral=True
            )

    @musicbot.subcommand(
        name="stop",
        description="Остановить музыкального бота"
    )
    async def stop_bot(
        self, 
        interaction: Interaction, 
        bot_id: str = SlashOption(
            name="bot_id",
            description="ID бота для остановки",
            required=True
        )
    ):
        """Останавливает музыкального бота"""
        # Проверяем, является ли пользователь администратором
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "У вас нет прав для использования этой команды!", 
                ephemeral=True
            )
        
        try:
            bot_id = int(bot_id)
        except ValueError:
            return await interaction.response.send_message(
                "Некорректный ID бота. Укажите правильный числовой ID.", 
                ephemeral=True
            )
        
        # Проверяем, существует ли бот с таким ID
        if bot_id not in self.music_bot_pool.bot_configs:
            return await interaction.response.send_message(
                f"Бот с ID {bot_id} не найден в пуле.", 
                ephemeral=True
            )
        
        # Проверяем, запущен ли бот
        if bot_id not in self.music_bot_pool.active_bots:
            return await interaction.response.send_message(
                f"Бот с ID {bot_id} не запущен.", 
                ephemeral=True
            )
        
        # Отправляем отложенный ответ
        await interaction.response.defer(ephemeral=True)
        
        # Останавливаем бота
        success = await self.music_bot_pool.stop_bot(bot_id)
        
        if success:
            await interaction.followup.send(
                f"Бот с ID {bot_id} успешно остановлен.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Не удалось остановить бота с ID {bot_id}.", 
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(MusicAdmin(bot)) 