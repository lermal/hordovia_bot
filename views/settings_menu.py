from nextcord import (
    Interaction, 
    Embed, 
    Color, 
    ui, 
    SelectOption,
    TextInputStyle,
    ButtonStyle
)
from nextcord.ui import Modal, View, Select
from typing import Optional, Dict, Any
import logging
from nextcord.ext import commands
from utils.settings_manager import SettingsManager
from logger import setup_logger
import nextcord

logger = setup_logger()

def format_setting_value(value):
    """Форматирует значение настройки для отображения"""
    if value is None:
        return ""
    elif isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    elif isinstance(value, bool):
        return "Да" if value else "Нет"
    else:
        return str(value)

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
            
            # Преобразуем значение в правильный тип данных
            converted_value = self._convert_value_to_proper_type(self.setting_key, new_value)
            
            # Обновляем настройку
            settings_manager = SettingsManager()
            settings_manager.set_setting(self.category, self.setting_key, converted_value)
            
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
    
    def _convert_value_to_proper_type(self, setting_key: str, value: str):
        """Преобразует строковое значение в правильный тип данных"""
        if not value or value.strip() == "":
            return value
        
        # Настройки, которые должны быть числами
        numeric_settings = {
            "notification_channel", "check_interval", "audio_quality", 
            "default_user_limit", "welcome_channel_id", "verification_channel_id", 
            "member_role_id", "rejected_role_id", "category_id", "create_channel_id"
        }
        
        # Настройки, которые должны быть списками
        list_settings = {"admin_role_ids", "load_exceptions", "allowed_categories"}
        
        # Настройки, которые должны быть булевыми значениями
        boolean_settings = {"enabled", "auto_reload"}
        
        if setting_key in numeric_settings:
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    logger.warning(f"Не удалось преобразовать '{value}' в число для настройки {setting_key}")
                    return value
        
        elif setting_key in list_settings:
            try:
                # Пытаемся разобрать как JSON список
                import json
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                # Если не получилось как JSON, пробуем разделить по запятым
                if "," in value:
                    # Разделяем по запятым и очищаем от пробелов
                    items = [item.strip() for item in value.split(",") if item.strip()]
                    # Для admin_role_ids преобразуем в числа
                    if setting_key == "admin_role_ids":
                        try:
                            return [int(item) for item in items if item.isdigit()]
                        except ValueError:
                            return items
                    # Для allowed_categories преобразуем в числа
                    elif setting_key == "allowed_categories":
                        try:
                            return [int(item) for item in items if item.isdigit()]
                        except ValueError:
                            return items
                    return items
                else:
                    # Если нет запятых, возвращаем как список с одним элементом
                    if setting_key == "admin_role_ids" and value.isdigit():
                        return [int(value)]
                    elif setting_key == "allowed_categories" and value.isdigit():
                        return [int(value)]
                    return [value] if value else []
        
        elif setting_key in boolean_settings:
            value_lower = value.lower()
            if value_lower in ("true", "1", "yes", "on"):
                return True
            elif value_lower in ("false", "0", "no", "off"):
                return False
            else:
                logger.warning(f"Не удалось преобразовать '{value}' в булево значение для настройки {setting_key}")
                return value
        
        # Для остальных настроек возвращаем как строку
        return value

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
                    value=format_setting_value(value),
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
            current_value = format_setting_value(current_settings.get(setting_key, ""))
            
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
            current_value = format_setting_value(current_settings.get(setting_key, ""))
            
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
            current_value = format_setting_value(current_settings.get(setting_key, ""))
            
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
                ),
                SelectOption(
                    label="Разрешенные категории",
                    value="allowed_categories",
                    description="Управление категориями для удаления комнат",
                    emoji="🔒"
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
            
            # Специальная обработка для allowed_categories
            if setting_key == "allowed_categories":
                await self.show_categories_management(interaction)
                return
            
            current_value = format_setting_value(current_settings.get(setting_key, ""))
            
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
    
    async def show_categories_management(self, interaction: Interaction):
        """Показывает интерфейс управления разрешенными категориями"""
        try:
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            embed = Embed(
                title="🔒 Управление разрешенными категориями",
                color=Color.blue()
            )
            
            if not allowed_categories:
                embed.description = "⚠️ **Нет разрешенных категорий для удаления!**\n" \
                                    "• Удаление приватных комнат **ЗАПРЕЩЕНО** во всех категориях"
            else:
                category_list = []
                for category_id in allowed_categories:
                    category = interaction.guild.get_channel(category_id)
                    if category:
                        category_list.append(f"• **{category.name}** (ID: {category_id})")
                    else:
                        category_list.append(f"• *Неизвестная категория* (ID: {category_id})")
                
                embed.description = "\n".join(category_list)
                embed.add_field(
                    name="Всего категорий",
                    value=str(len(allowed_categories)),
                    inline=True
                )
            
            view = CategoriesManagementView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Ошибка при показе управления категориями: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при загрузке управления категориями",
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
                    label="ID роли при отмене",
                    value="rejected_role_id",
                    description="ID роли, которая выдается при отклонении верификации",
                    emoji="❌"
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
            current_value = format_setting_value(current_settings.get(setting_key, ""))
            
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

# View для управления разрешенными категориями
class CategoriesManagementView(View):
    def __init__(self):
        super().__init__(timeout=180)
        
        self.add_item(CategorySelectDropdown())
        self.add_item(ClearCategoriesButton())
        self.add_item(RefreshCategoriesButton())

class CategorySelectDropdown(Select):
    def __init__(self):
        super().__init__(
            placeholder="Выберите действие с категорией",
            options=[
                SelectOption(
                    label="Добавить категорию",
                    value="add",
                    description="Добавить категорию в разрешенные",
                    emoji="➕"
                ),
                SelectOption(
                    label="Удалить категорию",
                    value="remove",
                    description="Удалить категорию из разрешенных",
                    emoji="➖"
                )
            ],
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: Interaction):
        try:
            action = self.values[0]
            
            if action == "add":
                await self.show_add_category_modal(interaction)
            elif action == "remove":
                await self.show_remove_category_dropdown(interaction)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке выбора действия: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обработке выбора",
                ephemeral=True
            )
    
    async def show_add_category_modal(self, interaction: Interaction):
        """Показывает модальное окно для добавления категории"""
        modal = AddCategoryModal()
        await interaction.response.send_modal(modal)
    
    async def show_remove_category_dropdown(self, interaction: Interaction):
        """Показывает выпадающий список категорий для удаления"""
        try:
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            if not allowed_categories:
                await interaction.response.send_message(
                    "❌ Нет категорий для удаления!",
                    ephemeral=True
                )
                return
            
            options = []
            for category_id in allowed_categories:
                category = interaction.guild.get_channel(category_id)
                if category:
                    options.append(SelectOption(
                        label=category.name,
                        value=str(category_id),
                        description=f"ID: {category_id}",
                        emoji="📁"
                    ))
            
            if not options:
                await interaction.response.send_message(
                    "❌ Нет доступных категорий для удаления!",
                    ephemeral=True
                )
                return
            
            view = View(timeout=180)
            view.add_item(RemoveCategorySelect(options))
            await interaction.response.send_message(
                "Выберите категорию для удаления:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Ошибка при показе списка категорий для удаления: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при загрузке списка категорий",
                ephemeral=True
            )

class RemoveCategorySelect(Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Выберите категорию для удаления",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: Interaction):
        try:
            category_id = int(self.values[0])
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            if category_id in allowed_categories:
                allowed_categories.remove(category_id)
                settings_manager.set_setting("private_rooms", "allowed_categories", allowed_categories)
                
                category = interaction.guild.get_channel(category_id)
                category_name = category.name if category else f"ID: {category_id}"
                
                await interaction.response.send_message(
                    f"✅ Категория **{category_name}** удалена из списка разрешенных!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Эта категория не находится в списке разрешенных!",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Ошибка при удалении категории: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при удалении категории",
                ephemeral=True
            )

class AddCategoryModal(Modal):
    def __init__(self):
        super().__init__(title="Добавить категорию")
        
        self.category_input = ui.TextInput(
            label="ID категории",
            placeholder="Введите ID категории для добавления",
            required=True,
            max_length=20
        )
        self.add_item(self.category_input)
    
    async def callback(self, interaction: Interaction):
        try:
            category_id = int(self.category_input.value)
            category = interaction.guild.get_channel(category_id)
            
            if not category or not isinstance(category, nextcord.CategoryChannel):
                await interaction.response.send_message(
                    "❌ Категория с таким ID не найдена!",
                    ephemeral=True
                )
                return
            
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            if category_id in allowed_categories:
                await interaction.response.send_message(
                    f"❌ Категория **{category.name}** уже находится в списке разрешенных!",
                    ephemeral=True
                )
                return
            
            allowed_categories.append(category_id)
            settings_manager.set_setting("private_rooms", "allowed_categories", allowed_categories)
            
            await interaction.response.send_message(
                f"✅ Категория **{category.name}** добавлена в список разрешенных!",
                ephemeral=True
            )
            
        except ValueError:
            await interaction.response.send_message(
                "❌ ID категории должен быть числом!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Ошибка при добавлении категории: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при добавлении категории",
                ephemeral=True
            )

class ClearCategoriesButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Очистить все",
            style=ButtonStyle.danger,
            emoji="🗑️"
        )
    
    async def callback(self, interaction: Interaction):
        try:
            settings_manager = SettingsManager()
            settings_manager.set_setting("private_rooms", "allowed_categories", [])
            
            await interaction.response.send_message(
                "⚠️ **Список категорий очищен!**\n"
                "Теперь удаление приватных комнат **ЗАПРЕЩЕНО** во всех категориях!",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Ошибка при очистке категорий: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при очистке категорий",
                ephemeral=True
            )

class RefreshCategoriesButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Обновить",
            style=ButtonStyle.secondary,
            emoji="🔄"
        )
    
    async def callback(self, interaction: Interaction):
        try:
            settings_manager = SettingsManager()
            current_settings = settings_manager.get_all_settings().get("private_rooms", {})
            allowed_categories = current_settings.get("allowed_categories", [])
            
            embed = Embed(
                title="🔒 Управление разрешенными категориями",
                color=Color.blue()
            )
            
            if not allowed_categories:
                embed.description = "⚠️ **Нет разрешенных категорий для удаления!**\n" \
                                    "• Приватные комнаты можно создавать в любых категориях\n" \
                                    "• Удаление приватных комнат **ЗАПРЕЩЕНО** во всех категориях"
            else:
                category_list = []
                for category_id in allowed_categories:
                    category = interaction.guild.get_channel(category_id)
                    if category:
                        category_list.append(f"• **{category.name}** (ID: {category_id})")
                    else:
                        category_list.append(f"• *Неизвестная категория* (ID: {category_id})")
                
                embed.description = "\n".join(category_list)
                embed.add_field(
                    name="Всего категорий",
                    value=str(len(allowed_categories)),
                    inline=True
                )
            
            view = CategoriesManagementView()
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении списка категорий: {str(e)}")
            await interaction.response.send_message(
                "❌ Произошла ошибка при обновлении списка",
                ephemeral=True
            ) 