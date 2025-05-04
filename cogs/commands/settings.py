from nextcord import (
    Interaction, 
    Embed, 
    Color, 
    slash_command, 
    Permissions
)
from nextcord.ext import commands
from nextcord.ext.commands import Cog
from bot import Bot
from config import GUILD_IDS
from utils.settings_manager import SettingsManager
from views.settings_menu import (
    SettingsCategoryView,
    MusicSettingsView,
    TwitchSettingsView,
    GeneralSettingsView,
    PrivateRoomsSettingsView,
    VerificationSettingsView,
    EditSettingModal
)
import logging

logger = logging.getLogger(__name__)

class SettingsCommand(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_manager = SettingsManager()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Команда настроек готова!")

    @slash_command(
        name="settings",
        description="Управление настройками бота",
        guild_ids=GUILD_IDS,
        default_member_permissions=Permissions(administrator=True)
    )
    async def settings(self, interaction: Interaction):
        """Команда для управления настройками бота"""
        try:
            # Отправляем начальное меню выбора категории
            view = SettingsCategoryView()
            await interaction.response.send_message(
                "Выберите категорию настроек:",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды /settings: {e}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при выполнении команды",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_select_option(self, interaction: Interaction):
        """Обработчик выбора опции в меню"""
        try:
            # Получаем выбранное значение
            selected_value = interaction.data["values"][0]
            
            # Определяем категорию по значению
            if selected_value in ["music", "twitch", "general", "private_rooms", "verification"]:
                category = selected_value
                current_settings = self.settings_manager.get_all_settings().get(category, {})
                
                # Создаем embed с текущими настройками
                embed = Embed(
                    title=f"Текущие настройки {category}",
                    color=Color.blue()
                )
                
                # Добавляем текущие настройки в embed
                for key, value in current_settings.items():
                    embed.add_field(
                        name=key,
                        value=str(value) if value else "Не установлено",
                        inline=False
                    )
                
                if category == "music":
                    view = MusicSettingsView()
                elif category == "twitch":
                    view = TwitchSettingsView()
                elif category == "general":
                    view = GeneralSettingsView()
                elif category == "private_rooms":
                    view = PrivateRoomsSettingsView()
                elif category == "verification":
                    view = VerificationSettingsView()
                else:
                    return
                
                await interaction.response.edit_message(
                    embed=embed,
                    view=view
                )
            
            # Если это выбор конкретной настройки
            else:
                # Получаем категорию из custom_id
                custom_id = interaction.data["custom_id"]
                if ":" in custom_id:
                    category = custom_id.split(":")[0]
                else:
                    category = custom_id
                
                setting_key = selected_value
                current_settings = self.settings_manager.get_all_settings().get(category, {})
                current_value = str(current_settings.get(setting_key, ""))
                
                modal = EditSettingModal(
                    setting_key=setting_key,
                    current_value=current_value
                )
                
                await interaction.response.send_modal(modal)
        
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора опции: {str(e)}")
            await interaction.response.send_message(
                "Произошла ошибка при обработке выбора.",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_modal_submit(self, interaction: Interaction):
        """Обработчик отправки модального окна"""
        try:
            category = interaction.data["custom_id"].split("_")[0]
            setting_key = interaction.data["components"][0]["components"][0]["custom_id"]
            new_value = interaction.data["components"][0]["components"][0]["value"]
            
            # Обновляем настройку
            self.settings_manager.set_setting(category, setting_key, new_value)
            
            await interaction.response.send_message(
                f"✅ Настройка {setting_key} успешно обновлена!",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке модального окна: {str(e)}")
            await interaction.response.send_message(
                "Произошла ошибка при сохранении настроек.",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(SettingsCommand(bot)) 