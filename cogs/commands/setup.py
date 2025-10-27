from nextcord import Interaction, Permissions, CategoryChannel, VoiceChannel
from nextcord.ext.commands import Cog
from nextcord import slash_command
from database import Database
from config import GUILD_IDS
from utils.settings_manager import settings_manager

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
                    # Проверяем, есть ли категория в разрешенных
                    current_settings = settings_manager.get_all_settings().get("private_rooms", {})
                    allowed_categories = current_settings.get("allowed_categories", [])
                    
                    if existing_category.id not in allowed_categories:
                        allowed_categories.append(existing_category.id)
                        settings_manager.set_setting("private_rooms", "allowed_categories", allowed_categories)
                        message = f"✅ Система уже настроена! Используйте канал: {existing_channel.mention}\n\n🔒 Категория **{existing_category.name}** добавлена в список разрешенных для удаления приватных комнат."
                    else:
                        message = f"✅ Система уже настроена! Используйте канал: {existing_channel.mention}"
                    
                    return await interaction.response.send_message(message, ephemeral=True)

            # Сценарий 2 и 3: Создаем новые каналы
            category = await interaction.guild.create_category("🔒 Приватные комнаты")
            channel = await interaction.guild.create_voice_channel(
                "➕ Создать комнату",
                category=category
            )
            
            # Сохраняем в том же порядке, что и в private_rooms.py
            await self.db.update_channel(interaction.guild.id, channel.id, category.id)
            
            # Добавляем созданную категорию в список разрешенных для удаления
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            if category.id not in allowed_categories:
                allowed_categories.append(category.id)
                settings_manager.set_setting("private_rooms", "allowed_categories", allowed_categories)
            
            # Обновление кэша PrivateRoomsCog модуля
            private_rooms_cog = self.bot.get_cog("PrivateRoomsCog")
            if private_rooms_cog:
                private_rooms_cog.guild_data[interaction.guild.id] = (channel.id, category.id)

            await interaction.response.send_message(
                f"✅ Настройка завершена! Используйте канал: {channel.mention}\n\n"
                f"🔒 Категория **{category.name}** автоматически добавлена в список разрешенных для удаления приватных комнат.",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Критическая ошибка: {str(e)}",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(SetupCommand(bot))