from nextcord import Interaction, Permissions, CategoryChannel, VoiceChannel
from nextcord.ext.commands import Cog
from nextcord import slash_command
from database import Database
from config import GUILD_IDS

class SetupCommand(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @slash_command(
        name="setup",
        description="Первоначальная настройка приватных комнат",
        guild_ids=GUILD_IDS,
        default_member_permissions=Permissions(administrator=True)
    )
    async def setup_command(self, interaction: Interaction):
        """Умная настройка системных каналов с проверкой состояний"""
        try:
            await self.db.connect()
            db_data = await self.db.get_guild_channels(interaction.guild.id)
            
            # Проверка существования каналов на сервере
            existing_category = interaction.guild.get_channel(db_data[1]) if db_data else None
            existing_channel = interaction.guild.get_channel(db_data[0]) if db_data else None

            # Сценарий 1: Каналы существуют и в БД, и на сервере
            if db_data and existing_category and existing_channel:
                return await interaction.response.send_message(
                    f"✅ Система уже настроена! Используйте канал: {existing_channel.mention}",
                    ephemeral=True
                )

            # Сценарий 2: Каналы есть в БД, но отсутствуют на сервере
            if db_data and (not existing_category or not existing_channel):
                category = await interaction.guild.create_category("🔒 Приватные комнаты")
                channel = await interaction.guild.create_voice_channel(
                    "➕ Создать комнату",
                    category=category
                )
                await self.db.update_channel(interaction.guild.id, channel.id, category.id)
                return await interaction.response.send_message(
                    f"🔨 Каналы восстановлены! Новый канал: {channel.mention}",
                    ephemeral=True
                )

            # Сценарий 3: Полная новая настройка
            category = await interaction.guild.create_category("🔒 Приватные комнаты")
            channel = await interaction.guild.create_voice_channel(
                "➕ Создать комнату",
                category=category
            )
            await self.db.update_channel(interaction.guild.id, channel.id, category.id)
            await interaction.response.send_message(
                f"✅ Настройка завершена! Категория: {category.mention}",
                ephemeral=True
            )

            # Обновление кэша Voice модуля
            voice_cog = self.bot.get_cog("Voice")
            if voice_cog:
                voice_cog.guild_data[interaction.guild.id] = (channel.id, category.id)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Критическая ошибка: {str(e)}",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(SetupCommand(bot))