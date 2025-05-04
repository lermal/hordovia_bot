from nextcord import (
    Interaction, 
    Embed, 
    Color, 
    ui, 
    SelectOption,
    TextInputStyle
)
from nextcord.ui import Modal, View, Select
from typing import Optional, Dict, Any
import logging
from nextcord.ext import commands
from utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

# Модальное окно для изменения настройки
class EditSettingModal(Modal):
    def __init__(self, setting_key: str, current_value: str = "", category: str = ""):
        # Ограничиваем длину заголовка до 45 символов
        title = f"Изменение {setting_key[:30]}"
        super().__init__(title=title)
        self.setting_key = setting_key
        self.current_value = current_value
        self.category = category
        
        self.value_input = ui.TextInput(
            label="Новое значение",
            placeholder="Введите новое значение",
            required=True,
            max_length=1000,
            default_value=current_value
        )
        self.add_item(self.value_input)
    
    async def callback(self, interaction: Interaction):
        try:
            new_value = self.value_input.value
            
            # Обновляем настройку
            settings_manager = SettingsManager()
            settings_manager.set_setting(self.category, self.setting_key, new_value)
            
            # Если это настройки приватных каналов, применяем изменения
            if self.category == "private_rooms":
                if self.setting_key == "default_category_name":
                    # Получаем категорию приватных каналов
                    category = interaction.guild.get_channel(settings_manager.get_setting("private_rooms", "category_id"))
                    if category:
                        await category.edit(name=new_value)
                
                elif self.setting_key == "default_create_channel_name":
                    # Получаем канал создания
                    create_channel = interaction.guild.get_channel(settings_manager.get_setting("private_rooms", "create_channel_id"))
                    if create_channel:
                        await create_channel.edit(name=new_value)
            
            await interaction.response.send_message(
                f"✅ Настройка {self.setting_key} успешно обновлена!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при сохранении настройки: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при сохранении настройки",
                ephemeral=True
            )

# View для выбора категории настроек
class SettingsCategoryView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.category_select = Select(
            placeholder="Выберите категорию настроек",
            options=[
                SelectOption(
                    label="Музыкальные настройки",
                    value="music",
                    description="Настройки музыкального бота",
                    emoji="🎵"
                ),
                SelectOption(
                    label="Настройки Twitch",
                    value="twitch",
                    description="Настройки интеграции с Twitch",
                    emoji="📺"
                ),
                SelectOption(
                    label="Общие настройки",
                    value="general",
                    description="Общие настройки бота",
                    emoji="⚙️"
                ),
                SelectOption(
                    label="Приватные комнаты",
                    value="private_rooms",
                    description="Настройки приватных комнат",
                    emoji="🔒"
                ),
                SelectOption(
                    label="Papers Please",
                    value="verification",
                    description="Настройки верификации новых участников",
                    emoji="📝"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.category_select.callback = self.on_category_select
        self.add_item(self.category_select)
    
    async def on_category_select(self, interaction: Interaction):
        try:
            category = self.category_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get(category, {})
            
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
                content="Выберите настройку для изменения:",
                embed=embed,
                view=view
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора категории: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )

# View для музыкальных настроек
class MusicSettingsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.settings_select = Select(
            placeholder="Выберите настройку",
            options=[
                SelectOption(
                    label="Формат аудио",
                    value="audio_format",
                    description="Настройка формата аудио (mp3, wav и т.д.)",
                    emoji="🎵"
                ),
                SelectOption(
                    label="Качество аудио",
                    value="audio_quality",
                    description="Настройка качества аудио (192, 256, 320)",
                    emoji="🔊"
                ),
                SelectOption(
                    label="Путь к FFmpeg",
                    value="ffmpeg_path",
                    description="Настройка пути к FFmpeg",
                    emoji="🔧"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.settings_select.callback = self.on_setting_select
        self.add_item(self.settings_select)
    
    async def on_setting_select(self, interaction: Interaction):
        try:
            setting_key = self.settings_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("music", {})
            current_value = str(current_settings.get(setting_key, ""))
            
            modal = EditSettingModal(
                setting_key=setting_key,
                current_value=current_value,
                category="music"
            )
            
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора настройки музыки: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )

# View для настроек Twitch
class TwitchSettingsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.settings_select = Select(
            placeholder="Выберите настройку",
            options=[
                SelectOption(
                    label="ID канала уведомлений",
                    value="notification_channel",
                    description="ID канала для уведомлений о стримах",
                    emoji="📢"
                ),
                SelectOption(
                    label="Интервал проверки",
                    value="check_interval",
                    description="Интервал проверки стримов в минутах",
                    emoji="⏱️"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.settings_select.callback = self.on_setting_select
        self.add_item(self.settings_select)
    
    async def on_setting_select(self, interaction: Interaction):
        try:
            setting_key = self.settings_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("twitch", {})
            current_value = str(current_settings.get(setting_key, ""))
            
            modal = EditSettingModal(
                setting_key=setting_key,
                current_value=current_value,
                category="twitch"
            )
            
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора настройки Twitch: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )

# View для общих настроек
class GeneralSettingsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.settings_select = Select(
            placeholder="Выберите настройку",
            options=[
                SelectOption(
                    label="Уровень логирования",
                    value="log_level",
                    description="Настройка уровня логирования",
                    emoji="📝"
                ),
                SelectOption(
                    label="Исключения при загрузке",
                    value="load_exceptions",
                    description="Настройка исключений при загрузке когов",
                    emoji="⚠️"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.settings_select.callback = self.on_setting_select
        self.add_item(self.settings_select)
    
    async def on_setting_select(self, interaction: Interaction):
        try:
            setting_key = self.settings_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("general", {})
            current_value = str(current_settings.get(setting_key, ""))
            
            modal = EditSettingModal(
                setting_key=setting_key,
                current_value=current_value,
                category="general"
            )
            
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора настройки: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )

# View для настроек приватных комнат
class PrivateRoomsSettingsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.settings_select = Select(
            placeholder="Выберите настройку",
            options=[
                SelectOption(
                    label="Название категории",
                    value="default_category_name",
                    description="Название категории по умолчанию",
                    emoji="📁"
                ),
                SelectOption(
                    label="Название канала создания",
                    value="default_create_channel_name",
                    description="Название канала создания по умолчанию",
                    emoji="➕"
                ),
                SelectOption(
                    label="Лимит пользователей",
                    value="default_user_limit",
                    description="Лимит пользователей по умолчанию",
                    emoji="👥"
                ),
                SelectOption(
                    label="Шаблон названия",
                    value="room_name_template",
                    description="Шаблон названия комнаты",
                    emoji="🏷️"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.settings_select.callback = self.on_setting_select
        self.add_item(self.settings_select)
    
    async def on_setting_select(self, interaction: Interaction):
        try:
            setting_key = self.settings_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            current_value = str(current_settings.get(setting_key, ""))
            
            modal = EditSettingModal(
                setting_key=setting_key,
                current_value=current_value,
                category="private_rooms"
            )
            
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора настройки приватных комнат: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )

# View для настроек верификации
class VerificationSettingsView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.settings_select = Select(
            placeholder="Выберите настройку",
            options=[
                SelectOption(
                    label="ID канала приветствия",
                    value="welcome_channel_id",
                    description="ID канала для приветственных сообщений",
                    emoji="👋"
                ),
                SelectOption(
                    label="ID канала верификации",
                    value="verification_channel_id",
                    description="ID канала для проверки новых участников",
                    emoji="✅"
                ),
                SelectOption(
                    label="ID роли участника",
                    value="member_role_id",
                    description="ID роли, которая выдается после верификации",
                    emoji="👤"
                ),
                SelectOption(
                    label="ID ролей администраторов",
                    value="admin_role_ids",
                    description="ID ролей администраторов через запятую",
                    emoji="👑"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.settings_select.callback = self.on_setting_select
        self.add_item(self.settings_select)
    
    async def on_setting_select(self, interaction: Interaction):
        try:
            setting_key = self.settings_select.values[0]
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("verification", {})
            current_value = str(current_settings.get(setting_key, ""))
            
            modal = EditSettingModal(
                setting_key=setting_key,
                current_value=current_value,
                category="verification"
            )
            
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора настройки верификации: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            ) 