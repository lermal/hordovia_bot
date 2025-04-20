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
            if db_data:
                create_channel_id, category_id = db_data  # Правильный порядок распаковки
                existing_category = interaction.guild.get_channel(category_id)
                existing_channel = interaction.guild.get_channel(create_channel_id)

                # Сценарий 1: Каналы существуют и в БД, и на сервере
                if existing_category and existing_channel:
                    return await interaction.response.send_message(
                        f"✅ Система уже настроена! Используйте канал: {existing_channel.mention}",
                        ephemeral=True
                    )

            # Сценарий 2 и 3: Создаем новые каналы
            category = await interaction.guild.create_category("🔒 Приватные комнаты")
            channel = await interaction.guild.create_voice_channel(
                "➕ Создать комнату",
                category=category
            )
            
            # Сохраняем в том же порядке, что и в private_rooms.py
            await self.db.update_channel(interaction.guild.id, channel.id, category.id)
            
            # Обновление кэша PrivateRoomsCog модуля
            private_rooms_cog = self.bot.get_cog("PrivateRoomsCog")
            if private_rooms_cog:
                private_rooms_cog.guild_data[interaction.guild.id] = (channel.id, category.id)

            await interaction.response.send_message(
                f"✅ Настройка завершена! Используйте канал: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Критическая ошибка: {str(e)}",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(SetupCommand(bot))