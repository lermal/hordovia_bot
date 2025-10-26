from config import *
from bot import Bot
from nextcord import Interaction, ButtonStyle, File, Embed, Color, PermissionOverwrite, DMChannel
from nextcord.ext.commands import Cog
from nextcord.ui import View, Button, button
import aiohttp
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime
from typing import Dict, Any
import random
from utils.settings_manager import SettingsManager
import asyncio

from logger import setup_logger

logger = setup_logger()

# Путь к шрифту и паспортам
FONT_PATH = "fonts/ttf.ttf"
FONT_SIZE = 32
PASSPORTS_DIR = "images/passports"

# Кэш для шрифтов
_font_cache = {}

def normalize_admin_role_ids(admin_role_ids):
    """Нормализует admin_role_ids в список, независимо от входного типа"""
    if isinstance(admin_role_ids, int):
        return [admin_role_ids]
    elif isinstance(admin_role_ids, list):
        return admin_role_ids
    else:
        return []

def get_font(font_size=FONT_SIZE):
    if font_size not in _font_cache:
        try:
            _font_cache[font_size] = ImageFont.truetype(FONT_PATH, font_size)
        except:
            logger.error(f"Ошибка загрузки шрифта {FONT_PATH}, использую системный шрифт")
            _font_cache[font_size] = ImageFont.load_default()
    return _font_cache[font_size]

async def get_avatar(member):
    # Получаем URL аватарки (используем формат PNG)
    avatar_url = member.display_avatar.with_format("png").url
    
    # Скачиваем аватарку с таймаутом
    try:
        timeout = aiohttp.ClientTimeout(total=5)  # 5 секунд таймаут
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(avatar_url) as response:
                if response.status == 200:
                    avatar_data = await response.read()
                    # Преобразуем байты в изображение PIL
                    avatar = Image.open(BytesIO(avatar_data))
                    # Изменяем размер до 220x220
                    avatar = avatar.resize((220, 220), Image.Resampling.LANCZOS)
                    return avatar
    except Exception as e:
        logger.warning(f"Не удалось загрузить аватарку для {member.id}: {e}")
    return None

class VerificationView(View):
    def __init__(self, bot: Bot, member=None, passport_message_id=None, member_join_event=None):
        super().__init__(timeout=None)  # Персистентный View
        self.bot = bot
        self.member = member
        self.settings_manager = SettingsManager()
        self.member_join_event = member_join_event  # Ссылка на MemberJoinEvent для доступа к кэшу
        
        # Получаем настройки верификации из кэша если доступен, иначе напрямую
        if self.member_join_event:
            settings = self.member_join_event.get_cached_verification_settings()
        else:
            settings = self.settings_manager.get_all_settings().get("verification", {})
        
        self.member_role_id = settings.get("member_role_id", 0)
        
        self.passport_message_id = passport_message_id  # ID сообщения с паспортом в канале "Добро пожаловать"
        self.is_revoke_state = False

    def setup_initial_buttons(self):
        """Создает начальные кнопки Принять/Отклонить"""
        # Очищаем все элементы
        self.clear_items()
        
        # Формируем custom_id с данными пользователя
        member_id = self.member.id if self.member else 0
        passport_msg_id = self.passport_message_id or 0
        
        # Добавляем кнопки через декораторы (они уже созданы)
        accept_btn = Button(
            label="Принять", 
            style=ButtonStyle.green, 
            disabled=False, 
            custom_id=f"verification:accept:{member_id}:{passport_msg_id}"
        )
        accept_btn.callback = self.handle_accept
        self.add_item(accept_btn)
        
        reject_btn = Button(
            label="Отклонить", 
            style=ButtonStyle.red, 
            disabled=False, 
            custom_id=f"verification:reject:{member_id}:{passport_msg_id}"
        )
        reject_btn.callback = self.handle_reject
        self.add_item(reject_btn)

    def setup_revoke_button(self):
        """Создает кнопку Отозвать решение"""
        self.clear_items()
        
        # Формируем custom_id с данными пользователя
        member_id = self.member.id if self.member else 0
        passport_msg_id = self.passport_message_id or 0
        
        revoke_btn = Button(
            label="Отозвать решение", 
            style=ButtonStyle.gray, 
            disabled=False, 
            custom_id=f"verification:revoke:{member_id}:{passport_msg_id}"
        )
        revoke_btn.callback = self.handle_revoke
        self.add_item(revoke_btn)
        self.is_revoke_state = True

    def setup_cancel_revoke_button(self):
        """Создает кнопку Отменить отзыв (только для отклоненных)"""
        self.clear_items()
        
        # Формируем custom_id с данными пользователя
        member_id = self.member.id if self.member else 0
        passport_msg_id = self.passport_message_id or 0
        
        cancel_btn = Button(
            label="Отменить отзыв", 
            style=ButtonStyle.secondary, 
            disabled=False, 
            custom_id=f"verification:cancel_revoke:{member_id}:{passport_msg_id}"
        )
        cancel_btn.callback = self.handle_cancel_revoke
        self.add_item(cancel_btn)

    def reset_to_initial_state(self):
        """Сбрасывает View к исходному состоянию с кнопками Принять/Отклонить"""
        self.is_revoke_state = False
        self.setup_initial_buttons()
    
    async def restore_state_from_message(self, message):
        """Восстанавливает состояние View на основе данных из сообщения"""
        try:
            # Получаем member_id из embed'а сообщения
            if message.embeds:
                embed = message.embeds[0]
                # Ищем mention пользователя в description
                import re
                mention_match = re.search(r'<@(\d+)>', embed.description or "")
                if mention_match:
                    member_id = int(mention_match.group(1))
                    self.member = message.guild.get_member(member_id)
                    
                    # Проверяем существующие паспорта для определения состояния
                    accept_passport = os.path.join(PASSPORTS_DIR, f"{member_id}_accept.png")
                    deny_passport = os.path.join(PASSPORTS_DIR, f"{member_id}_deny.png")
                    empty_passport = os.path.join(PASSPORTS_DIR, f"{member_id}_empty.png")
                    
                    if os.path.exists(accept_passport) or os.path.exists(deny_passport):
                        # Пользователь уже обработан, показываем кнопку отзыва
                        self.setup_revoke_button()
                    elif os.path.exists(empty_passport):
                        # Пользователь ожидает верификации
                        self.setup_initial_buttons()
                    else:
                        # По умолчанию показываем начальные кнопки
                        self.setup_initial_buttons()
                        
                    # Ищем сообщение с паспортом в welcome канале для получения passport_message_id
                    await self.find_passport_message_by_member_id(member_id)
                        
                    logger.info(f"Восстановлено состояние View для пользователя {member_id}, passport_message_id: {self.passport_message_id}")
                    return True
        except Exception as e:
            logger.error(f"Ошибка при восстановлении состояния View: {e}")
        
        return False
    
    async def find_passport_message_by_member_id(self, member_id: int):
        """Ищет сообщение с паспортом для указанного member_id в welcome канале."""
        try:
            if self.member_join_event:
                settings = self.member_join_event.get_cached_verification_settings()
            else:
                settings = self.settings_manager.get_all_settings().get("verification", {})
            
            welcome_channel_id = settings.get("welcome_channel_id", 0)
            welcome_channel = self.bot.get_channel(welcome_channel_id)

            if welcome_channel:
                # Ищем сообщение с паспортом в последних сообщениях канала
                async for message in welcome_channel.history(limit=100):
                    if message.embeds:
                        embed = message.embeds[0]
                        # Ищем mention пользователя в description
                        import re
                        mention_match = re.search(r'<@(\d+)>', embed.description or "")
                        if mention_match and int(mention_match.group(1)) == member_id:
                            self.passport_message_id = message.id
                            logger.info(f"Найдено сообщение с паспортом для {member_id}, message_id: {self.passport_message_id}")
                            return
                logger.warning(f"Не найдено сообщение с паспортом для {member_id} в канале {welcome_channel.name}")
            else:
                logger.warning(f"Не найден канал приветствия с ID: {welcome_channel_id}")
        except Exception as e:
            logger.error(f"Ошибка при поиске сообщения с паспортом: {e}")
            self.passport_message_id = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Получаем настройки из кэша если доступен, иначе напрямую
        if self.member_join_event:
            settings = self.member_join_event.get_cached_verification_settings()
        else:
            settings = self.settings_manager.get_all_settings().get("verification", {})
        
        admin_role_ids = normalize_admin_role_ids(settings.get("admin_role_ids", []))
        
        has_permission = any(role.id in admin_role_ids for role in interaction.user.roles)
        if not has_permission:
            await interaction.response.send_message("У вас нет прав для выполнения этого действия!", ephemeral=True)
            return False
        return True

    async def check_existing_passport(self, member):
        # Проверяем оба варианта паспорта (принятый и отклоненный)
        accept_passport = os.path.join(PASSPORTS_DIR, f"{member.id}_accept.png")
        deny_passport = os.path.join(PASSPORTS_DIR, f"{member.id}_deny.png")
        empty_passport = os.path.join(PASSPORTS_DIR, f"{member.id}_empty.png")
        
        if os.path.exists(deny_passport):
            try:
                await member.send("Вам отказано в доступе к серверу.")
            except:
                pass
            await member.kick(reason="Ранее отклоненная заявка")
            return True
        elif os.path.exists(empty_passport):
            # Если есть пустой паспорт, значит пользователь уже в процессе верификации
            logger.info(f"Найден существующий пустой паспорт для {member.id}, пропускаем создание нового")
            return True
        elif os.path.exists(accept_passport):
            # Для принятых паспортов возвращаем False, чтобы обработка продолжилась в on_member_join
            return False
        return False

    async def handle_accept(self, interaction: Interaction):
        """Обработчик кнопки Принять"""
        # Восстанавливаем данные из custom_id
        await self.restore_from_custom_id(interaction)
        await self.accept(interaction)

    async def handle_reject(self, interaction: Interaction):
        """Обработчик кнопки Отклонить"""
        # Восстанавливаем данные из custom_id
        await self.restore_from_custom_id(interaction)
        await self.reject(interaction)

    async def handle_revoke(self, interaction: Interaction):
        """Обработчик кнопки Отозвать решение"""
        # Восстанавливаем данные из custom_id
        await self.restore_from_custom_id(interaction)
        await self.revoke_decision(interaction)

    async def handle_cancel_revoke(self, interaction: Interaction):
        """Обработчик кнопки Отменить отзыв"""
        # Восстанавливаем данные из custom_id
        await self.restore_from_custom_id(interaction)
        await self.cancel_revoke_decision(interaction)
    
    async def restore_from_custom_id(self, interaction: Interaction):
        """Восстанавливает member_id и passport_message_id из custom_id кнопки"""
        try:
            # Находим нажатую кнопку
            clicked_button = None
            for component in interaction.message.components:
                for item in component.children:
                    if hasattr(item, 'custom_id') and item.custom_id:
                        # Проверяем, была ли нажата эта кнопка (по interaction.data)
                        if interaction.data.get('custom_id') == item.custom_id:
                            clicked_button = item
                            break
                if clicked_button:
                    break
            
            if clicked_button and clicked_button.custom_id:
                # Парсим custom_id: "verification:action:member_id:passport_msg_id"
                parts = clicked_button.custom_id.split(':')
                if len(parts) >= 4:
                    member_id = int(parts[2])
                    passport_msg_id = int(parts[3]) if parts[3] != '0' else None
                    
                    # Восстанавливаем member
                    if not self.member or self.member.id != member_id:
                        self.member = interaction.guild.get_member(member_id)
                        if self.member:
                            logger.info(f"Восстановлен member {member_id} из custom_id")
                        else:
                            logger.warning(f"Не удалось найти member {member_id} на сервере")
                    
                    # Восстанавливаем passport_message_id
                    if passport_msg_id and passport_msg_id != self.passport_message_id:
                        self.passport_message_id = passport_msg_id
                        logger.info(f"Восстановлен passport_message_id {passport_msg_id} из custom_id")
                        
        except Exception as e:
            logger.error(f"Ошибка при восстановлении данных из custom_id: {e}")
            # Fallback к старому методу
            await self.restore_member_from_interaction(interaction)

    async def restore_member_from_interaction(self, interaction: Interaction):
        """Восстанавливает информацию о member из сообщения interaction"""
        try:
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                import re
                mention_match = re.search(r'<@(\d+)>', embed.description or "")
                if mention_match:
                    member_id = int(mention_match.group(1))
                    self.member = interaction.guild.get_member(member_id)
                    if self.member:
                        logger.info(f"Восстановлен member {member_id} из interaction")
                        # Также восстанавливаем passport_message_id если он отсутствует
                        if not self.passport_message_id:
                            await self.find_passport_message_by_member_id(member_id)
                    else:
                        logger.warning(f"Не удалось найти member {member_id} на сервере")
        except Exception as e:
            logger.error(f"Ошибка при восстановлении member из interaction: {e}")

    async def accept(self, interaction: Interaction):
        try:
            logger.info(f"Начинаем принятие пользователя {self.member.id}, passport_message_id: {self.passport_message_id}")
            
            # Отключаем кнопки во время обработки
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            # Обновляем сообщение с отключенными кнопками
            await interaction.message.edit(view=self)
            
            # Сразу отправляем ответ, чтобы не было таймаута
            try:
                await interaction.response.send_message(f"Обрабатываем принятие участника {self.member.mention}...", ephemeral=True)
            except Exception as e:
                logger.warning(f"Не удалось отправить первичный ответ: {e}")
            
            if self.is_revoke_state:
                # Отзываем решение
                await self.revoke_decision(interaction)
                return

            role = interaction.guild.get_role(self.member_role_id)
            
            if role:
                await self.member.add_roles(role)
                
                # Создаем паспорт с печатью принятия
                try:
                    passport_path = await self.create_stamped_passport(self.member, True)
                    # Удаляем пустой паспорт
                    empty_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_empty.png")
                    if os.path.exists(empty_passport):
                        os.remove(empty_passport)
                except Exception as e:
                    logger.error(f"Ошибка при создании паспорта: {e}")
                    try:
                        await interaction.followup.send("Произошла ошибка при создании паспорта. Попробуйте еще раз.", ephemeral=True)
                    except:
                        pass
                    return
                
                # Меняем кнопки на "Отозвать решение"
                self.setup_revoke_button()
                
                # Обновляем сообщение
                embed = Embed(
                    title="Участник принят",
                    description=f"Пользователь {self.member.mention} успешно принят на сервер!",
                    color=Color.green()
                )
                embed.add_field(name="ID", value=self.member.id)
                embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
                
                await interaction.message.edit(embed=embed, view=self)
                
                # Отправляем финальное уведомление
                try:
                    await interaction.followup.send(f"Участник {self.member.mention} успешно принят!", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить финальное уведомление: {e}")
                
                # Обновляем сообщение с паспортом в канале приветствия
                if self.member_join_event:
                    settings = self.member_join_event.get_cached_verification_settings()
                else:
                    settings = self.settings_manager.get_all_settings().get("verification", {})
                
                welcome_channel_id = settings.get("welcome_channel_id", 0)
                welcome_channel = self.bot.get_channel(welcome_channel_id)
                
                if welcome_channel and self.passport_message_id:
                    try:
                        logger.info(f"Обновляем сообщение с паспортом для {self.member.id}, message_id: {self.passport_message_id}")
                        passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                        welcome_embed = Embed(
                            title="Welcome to Hordovia!",
                            description=f"Добро пожаловать на территорию Хордовии, товарищ {self.member.mention}!\nДежурный {interaction.user.mention} проверил твою заявку.\nСлава Хордовии! Спасибо за борщ!",
                            color=Color.green()
                        )
                        welcome_embed.set_image(url="attachment://passport.png")
                        await passport_message.edit(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                        logger.info(f"Сообщение с паспортом успешно обновлено для {self.member.id}")
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении сообщения с паспортом для {self.member.id}: {e}")
                        logger.error(f"Channel ID: {welcome_channel_id}, Message ID: {self.passport_message_id}")
                else:
                    logger.warning(f"Не удалось найти канал или ID сообщения для обновления паспорта. Channel: {welcome_channel}, Message ID: {self.passport_message_id}")
        except Exception as e:
            logger.error(f"Ошибка в методе accept: {e}")
            try:
                await interaction.followup.send("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)
            except Exception as ex:
                logger.warning(f"Не удалось отправить сообщение об ошибке: {ex}")

    async def reject(self, interaction: Interaction):
        try:
            logger.info(f"Начинаем отклонение пользователя {self.member.id}, passport_message_id: {self.passport_message_id}")
            
            # Отключаем кнопки во время обработки
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            # Обновляем сообщение с отключенными кнопками
            await interaction.message.edit(view=self)
            
            # Сразу отправляем ответ, чтобы не было таймаута
            try:
                await interaction.response.send_message(f"Обрабатываем отклонение участника {self.member.mention}...", ephemeral=True)
            except Exception as e:
                logger.warning(f"Не удалось отправить первичный ответ: {e}")
            
            if self.is_revoke_state:
                # Отзываем решение
                await self.revoke_decision(interaction)
                return

            # Создаем паспорт с печатью отклонения
            try:
                passport_path = await self.create_stamped_passport(self.member, False)
                # Удаляем пустой паспорт
                empty_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_empty.png")
                if os.path.exists(empty_passport):
                    os.remove(empty_passport)
            except Exception as e:
                logger.error(f"Ошибка при создании паспорта: {e}")
                try:
                    await interaction.followup.send("Произошла ошибка при создании паспорта. Попробуйте еще раз.", ephemeral=True)
                except:
                    pass
                return
            
            # Меняем кнопки на "Отозвать решение"
            self.setup_revoke_button()
            
            # Обновляем сообщение
            embed = Embed(
                title="Участник отклонен",
                description=f"Пользователь {self.member.mention} был отклонен и становится <@&{self.rejected_role_id}>.",
                color=Color.red()
            )
            embed.add_field(name="ID", value=self.member.id)
            embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
            
            await interaction.message.edit(embed=embed, view=self)
            
            # Отправляем финальное уведомление
            try:
                await interaction.followup.send(f"Участник {self.member.mention} отклонен и получил роль ИНС.", ephemeral=True)
            except Exception as e:
                logger.warning(f"Не удалось отправить финальное уведомление: {e}")
            
            # Обновляем сообщение с паспортом в канале приветствия
            if self.member_join_event:
                settings = self.member_join_event.get_cached_verification_settings()
            else:
                settings = self.settings_manager.get_all_settings().get("verification", {})
            
            welcome_channel_id = settings.get("welcome_channel_id", 0)
            welcome_channel = self.bot.get_channel(welcome_channel_id)
            
            if welcome_channel and self.passport_message_id:
                try:
                    logger.info(f"Обновляем сообщение с паспортом для {self.member.id}, message_id: {self.passport_message_id}")
                    passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                    welcome_embed = Embed(
                        title="Welcome to Hordovia!",
                        description=f"Пользователь {self.member.mention} был отклонен дежурным {interaction.user.mention} и становится <@&{self.rejected_role_id}>.\nСлава Хордовии! Спасибо за борщ!",
                        color=Color.red()
                    )
                    welcome_embed.set_image(url="attachment://passport.png")
                    await passport_message.edit(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                    logger.info(f"Сообщение с паспортом успешно обновлено для {self.member.id}")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении сообщения с паспортом для {self.member.id}: {e}")
                    logger.error(f"Channel ID: {welcome_channel_id}, Message ID: {self.passport_message_id}")
            else:
                logger.warning(f"Не удалось найти канал или ID сообщения для обновления паспорта. Channel: {welcome_channel}, Message ID: {self.passport_message_id}")
            
            # Отправляем сообщение пользователю и кикаем его
            try:
                await self.member.send("Ваша заявка на вступление была отклонена.")
            except:
                pass
            await self.member.add_roles(interaction.guild.get_role(self.rejected_role_id))
        except Exception as e:
            logger.error(f"Ошибка в методе reject: {e}")
            try:
                await interaction.followup.send("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)
            except Exception as ex:
                logger.warning(f"Не удалось отправить сообщение об ошибке: {ex}")

    async def revoke_decision(self, interaction: Interaction):
        try:
            # Проверяем, нужно ли отправлять первичный ответ
            should_send_response = not interaction.response.is_done()
            
            # Отключаем кнопку во время обработки
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            # Обновляем сообщение с отключенной кнопкой
            await interaction.message.edit(view=self)
            
            if should_send_response:
                try:
                    await interaction.response.send_message("Обрабатываем отзыв решения...", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить первичный ответ в revoke_decision: {e}")
                    should_send_response = False
            
            # Проверяем, какое решение было принято
            accept_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_accept.png")
            deny_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_deny.png")
            
            was_accepted = os.path.exists(accept_passport)
            was_denied = os.path.exists(deny_passport)
            
            if was_accepted:
                # Пользователь был принят - отзываем принятие
                logger.info(f"Отзываем принятие пользователя {self.member.id}")
                
                # Удаляем принятый паспорт
                if os.path.exists(accept_passport):
                    os.remove(accept_passport)
                
                # Забираем роль хордовца
                role = interaction.guild.get_role(self.member_role_id)
                member = interaction.guild.get_member(self.member.id)
                if member and role and role in member.roles:
                    await member.remove_roles(role)
                    logger.info(f"Роль хордовца снята с пользователя {self.member.id}")
                
                # Удаляем старое сообщение и создаем новое с пустым паспортом
                if self.member_join_event:
                    settings = self.member_join_event.get_cached_verification_settings()
                else:
                    settings = self.settings_manager.get_all_settings().get("verification", {})
                
                welcome_channel_id = settings.get("welcome_channel_id", 0)
                welcome_channel = self.bot.get_channel(welcome_channel_id)
                
                if welcome_channel and self.passport_message_id:
                    try:
                        # Удаляем старое сообщение
                        old_message = await welcome_channel.fetch_message(self.passport_message_id)
                        await old_message.delete()
                        logger.info(f"Удалено старое сообщение с принятым паспортом для {self.member.id}")
                        
                        # Создаем пустой паспорт
                        empty_passport_path = await self.create_empty_passport(self.member)
                        
                        # Отправляем новое сообщение с пустым паспортом
                        welcome_embed = Embed(
                            title="Welcome to Hordovia!",
                            description=f"Добро пожаловать на территорию Хордовии, товарищ {self.member.mention}!\nСлава Хордовии! Спасибо за борщ!",
                            color=Color.blue()
                        )
                        welcome_embed.set_image(url="attachment://passport.png")
                        new_message = await welcome_channel.send(embed=welcome_embed, file=File(empty_passport_path, filename="passport.png"))
                        
                        # Обновляем ID сообщения
                        self.passport_message_id = new_message.id
                        logger.info(f"Создано новое сообщение с пустым паспортом для {self.member.id}, message_id: {new_message.id}")
                        
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении сообщения с паспортом: {e}")
                
                # Возвращаем кнопки принятия/отклонения (БЕЗ кнопки отмены отзыва)
                self.reset_to_initial_state()
                
                # Обновляем сообщение в канале верификации
                embed = Embed(
                    title="Принятие отозвано",
                    description=f"Принятие пользователя {self.member.mention} отозвано.\nПользователь возвращен к статусу ожидания верификации.",
                    color=Color.blue()
                )
                embed.add_field(name="ID", value=self.member.id)
                embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
                
                await interaction.message.edit(embed=embed, view=self)
                
                # Отправляем ответ через followup
                try:
                    await interaction.followup.send("Принятие пользователя отозвано. Пользователь возвращен к ожиданию верификации.", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить ответ на interaction: {e}")
                    # Игнорируем ошибки отправки ответа, главное что действие выполнено
            
            elif was_denied:
                # Пользователь был отклонен - отзываем отклонение
                logger.info(f"Отзываем отклонение пользователя {self.member.id}")
                
                # Удаляем отклоненный паспорт
                if os.path.exists(deny_passport):
                    os.remove(deny_passport)
                
                # Отправляем ЛС пользователю о том, что отклонение отменено
                try:
                    dm_embed = Embed(
                        title="Решение об отклонении отменено",
                        description=f"Привет! Решение об отклонении твоей заявки на сервер **{interaction.guild.name}** было отменено.\n\nТы можешь снова попытаться присоединиться к серверу.",
                        color=Color.green()
                    )
                    await self.member.send(embed=dm_embed)
                    logger.info(f"Отправлено ЛС пользователю {self.member.id} об отмене отклонения")
                except Exception as e:
                    logger.warning(f"Не удалось отправить ЛС пользователю {self.member.id}: {e}")
                
                # Создаем кнопку "Отменить отзыв"
                self.setup_cancel_revoke_button()
                
                self.is_revoke_state = True
                
                # Обновляем сообщение в канале верификации
                embed = Embed(
                    title="Отклонение отозвано",
                    description=f"Отклонение пользователя {self.member.mention} отозвано.\nПользователю отправлено уведомление в личные сообщения.",
                    color=Color.orange()
                )
                embed.add_field(name="ID", value=self.member.id)
                embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
                
                await interaction.message.edit(embed=embed, view=self)
                
                try:
                    await interaction.followup.send("Отклонение пользователя отозвано. Пользователь уведомлен в ЛС.", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить ответ на interaction: {e}")
                    # Игнорируем ошибки отправки ответа, главное что действие выполнено
            
            else:
                # Неизвестное состояние
                logger.warning(f"Попытка отозвать решение для пользователя {self.member.id}, но паспорт не найден")
                try:
                    await interaction.followup.send("Не найден паспорт для отзыва решения.", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить ответ на interaction: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка в методе revoke_decision: {e}")
            try:
                await interaction.followup.send("Произошла ошибка при отзыве решения. Попробуйте еще раз.", ephemeral=True)
            except Exception as ex:
                logger.warning(f"Не удалось отправить сообщение об ошибке: {ex}")

    async def cancel_revoke_decision(self, interaction: Interaction):
        """Отменяет отзыв (удаляет сообщение) - только для отклоненных пользователей"""
        try:
            # Отключаем кнопку во время обработки
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            # Обновляем сообщение с отключенной кнопкой
            await interaction.message.edit(view=self)
            
            # Отправляем ответ
            try:
                await interaction.response.send_message("Удаляем сообщение верификации...", ephemeral=True)
            except Exception as e:
                logger.warning(f"Не удалось отправить ответ: {e}")
            
            # Удаляем сообщение верификации
            await interaction.message.delete()
            logger.info(f"Удалено сообщение верификации для пользователя {self.member.id} по запросу отмены отзыва")
                
        except Exception as e:
            logger.error(f"Ошибка в методе cancel_revoke_decision: {e}")
            try:
                await interaction.followup.send("Произошла ошибка при удалении сообщения.", ephemeral=True)
            except:
                pass

    async def create_empty_passport(self, member):
        """Создает пустой паспорт для пользователя"""
        try:
            # Проверяем существование директории для шаблонов
            if not os.path.exists("images/passport_template"):
                os.makedirs("images/passport_template")
            
            # Проверяем существование необходимых файлов
            template_path = "images/passport_template/new-passport.png"
            
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Не найден файл шаблона паспорта: {template_path}")
            
            # Создаем базовый паспорт
            img = Image.open(template_path)
            draw = ImageDraw.Draw(img)
            
            # Загружаем аватарку асинхронно, но не ждем её
            avatar_task = asyncio.create_task(get_avatar(member))
            
            # Добавляем информацию на паспорт (это быстро)
            draw.text((40, img.height - 390), member.name, font=get_font(64), fill="#584a48")
            draw.text((370, img.height - 338), f"{member.created_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((370, img.height - 285), f"{member.joined_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((40, img.height - 83), f"{member.id}", font=get_font(60), fill="#584a48")
            
            # Теперь ждем аватарку (если она еще загружается)
            try:
                avatar = await asyncio.wait_for(avatar_task, timeout=3.0)  # Ждем максимум 3 секунды
                if avatar:
                    # Вставляем аватарку в паспорт
                    avatar_x = 40
                    avatar_y = 550
                    img.paste(avatar, (avatar_x, avatar_y))
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут загрузки аватарки для {member.id}")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении аватарки для {member.id}: {e}")
            
            # Сохраняем результат
            passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}_empty.png")
            img.save(passport_path, optimize=True)  # Оптимизируем сохранение
            return passport_path
        except Exception as e:
            logger.error(f"Ошибка при создании пустого паспорта: {e}")
            raise

    async def create_stamped_passport(self, member, accepted: bool):
        try:
            logger.info(f"Создаем паспорт с печатью для {member.id}, accepted: {accepted}")
            
            # Проверяем существование директории для шаблонов
            if not os.path.exists("images/passport_template"):
                os.makedirs("images/passport_template")
            
            # Проверяем существование директории для паспортов
            if not os.path.exists(PASSPORTS_DIR):
                os.makedirs(PASSPORTS_DIR)
            
            # Проверяем существование необходимых файлов
            template_path = "images/passport_template/new-passport.png"
            stamp_path = "images/passport_template/press_yes.png" if accepted else "images/passport_template/press_no.png"
            
            logger.info(f"Проверяем файлы: template={template_path}, stamp={stamp_path}")
            
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Не найден файл шаблона паспорта: {template_path}")
            if not os.path.exists(stamp_path):
                raise FileNotFoundError(f"Не найден файл печати: {stamp_path}")
            
            logger.info("Все файлы найдены, начинаем создание паспорта")
            
            # Создаем базовый паспорт
            img = Image.open(template_path)
            draw = ImageDraw.Draw(img)
            
            # Загружаем аватарку асинхронно, но не ждем её
            avatar_task = asyncio.create_task(get_avatar(member))
            
            # Добавляем информацию на паспорт (это быстро)
            draw.text((40, img.height - 390), member.name, font=get_font(64), fill="#584a48")
            draw.text((370, img.height - 338), f"{member.created_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((370, img.height - 285), f"{member.joined_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((40, img.height - 83), f"{member.id}", font=get_font(60), fill="#584a48")
            
            # Добавляем печать
            stamp_img = Image.open(stamp_path)
            
            # Добавляем дату на печать
            stamp_draw = ImageDraw.Draw(stamp_img)
            current_date = datetime.now().strftime("%d %B, %Y")
            stamp_font = get_font(48)
            stamp_draw.text((120, 35), current_date, font=stamp_font, anchor="mm", fill="#047907" if accepted else "#ff9600")
            
            # Рандомный поворот печати
            rotation_angle = random.randint(-10, 10)
            rotated_stamp = stamp_img.rotate(rotation_angle, expand=True, resample=Image.BICUBIC)
            
            # Рандомное смещение
            base_x, base_y = 130, 100
            random_offset_x = random.randint(-15, 15)
            random_offset_y = random.randint(-15, 15)
            stamp_position = (base_x + random_offset_x, base_y + random_offset_y)
            
            # Накладываем печать
            img.paste(rotated_stamp, stamp_position, rotated_stamp if rotated_stamp.mode == 'RGBA' else None)
            
            # Теперь ждем аватарку (если она еще загружается)
            try:
                avatar = await asyncio.wait_for(avatar_task, timeout=3.0)  # Ждем максимум 3 секунды
                if avatar:
                    # Вставляем аватарку в паспорт
                    avatar_x = 40
                    avatar_y = 550
                    img.paste(avatar, (avatar_x, avatar_y))
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут загрузки аватарки для {member.id}")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении аватарки для {member.id}: {e}")
            
            # Сохраняем результат
            suffix = "_accept" if accepted else "_deny"
            passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}{suffix}.png")
            img.save(passport_path, optimize=True)  # Оптимизируем сохранение
            logger.info(f"Паспорт успешно создан и сохранен: {passport_path}")
            return passport_path
        except Exception as e:
            logger.error(f"Ошибка при создании паспорта: {e}")
            raise


class MemberJoinEvent(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.settings_manager = SettingsManager()
        
        # Кэшируем настройки верификации
        self._cached_verification_settings = self.settings_manager.get_all_settings().get("verification", {})
        
        # Подписываемся на изменения настроек верификации
        self.settings_manager.subscribe_to_category("verification", self._update_verification_cache)
        
        # Создаем директорию для паспортов, если её нет
        if not os.path.exists(PASSPORTS_DIR):
            os.makedirs(PASSPORTS_DIR)
        
        # Словарь для отслеживания обрабатываемых пользователей (предотвращает дублирование)
        self.processing_users = set()
    
    def _update_verification_cache(self, new_settings: Dict[str, Any]):
        """Обновляет кэш настроек верификации"""
        self._cached_verification_settings = new_settings
        logger.info("Кэш настроек верификации обновлен")
    
    def get_cached_verification_settings(self) -> Dict[str, Any]:
        """Возвращает кэшированные настройки верификации"""
        return self._cached_verification_settings
    
    async def register_persistent_views(self):
        """Регистрирует персистентные View для верификации после загрузки кога"""
        try:
            settings = self.get_cached_verification_settings()
            verification_channel_id = settings.get("verification_channel_id", 0)
            
            if verification_channel_id:
                verification_channel = self.bot.get_channel(verification_channel_id)
                if verification_channel:
                    # Ищем сообщения с компонентами View в канале верификации
                    async for message in verification_channel.history(limit=100):
                        if message.components and message.author == self.bot.user:
                            # Создаем новый View и восстанавливаем его состояние
                            view = VerificationView(self.bot, member_join_event=self)
                            if await view.restore_state_from_message(message):
                                # Регистрируем восстановленный View
                                self.bot.add_view(view, message_id=message.id)
                                logger.info(f"Зарегистрирован персистентный View для сообщения {message.id}")
            
            logger.info("Регистрация персистентных View завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при регистрации персистентных View: {e}")
    
    @Cog.listener()
    async def on_ready(self):
        """Регистрируем персистентные View после готовности бота"""
        await self.register_persistent_views()

    @Cog.listener()
    async def on_member_join(self, member):
        # Проверяем, не обрабатывается ли уже этот пользователь
        if member.id in self.processing_users:
            logger.warning(f"Пользователь {member.id} уже обрабатывается, пропускаем")
            return
        
        try:
            # Добавляем пользователя в обработку
            self.processing_users.add(member.id)
            
            # Получаем кэшированные настройки верификации
            settings = self.get_cached_verification_settings()
            admin_role_ids = normalize_admin_role_ids(settings.get("admin_role_ids", []))
            
            welcome_channel_id = settings.get("welcome_channel_id", 0)
            verification_channel_id = settings.get("verification_channel_id", 0)
            member_role_id = settings.get("member_role_id", 0)
            rejected_role_id = settings.get("rejected_role_id", 0)
            
            # Проверяем, есть ли уже принятый паспорт (для возвращающихся пользователей)
            accepted_passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}_accept.png")
            rejected_passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}_deny.png")
            
            if os.path.exists(accepted_passport_path):
                # Пользователь возвращается с принятым паспортом
                logger.info(f"Пользователь {member.id} возвращается с принятым паспортом")
                
                # Выдаем роль хордовца
                if member_role_id:
                    role = member.guild.get_role(member_role_id)
                    if role:
                        await member.add_roles(role)
                        logger.info(f"Выдана роль хордовца пользователю {member.id}")
                
                # Отправляем сообщение и паспорт в канал приветствия
                welcome_channel = self.bot.get_channel(welcome_channel_id)
                if welcome_channel:
                    embed = Embed(
                        title="Хордовец вернулся!",
                        description=f"Хордовец {member.mention} вернулся на сервер!\nДобро пожаловать домой, товарищ!",
                        color=Color.green()
                    )
                    
                    # Отправляем сообщение с паспортом
                    if os.path.exists(accepted_passport_path):
                        embed.set_image(url="attachment://passport.png")
                        await welcome_channel.send(
                            embed=embed, 
                            file=File(accepted_passport_path, filename="passport.png")
                        )
                        logger.info(f"Отправлено сообщение о возвращении хордовца {member.id} с паспортом")
                    else:
                        # Если файл паспорта не найден, отправляем просто сообщение
                        await welcome_channel.send(embed=embed)
                        logger.info(f"Отправлено сообщение о возвращении хордовца {member.id} без паспорта")
                else:
                    logger.warning(f"Не найден канал приветствия с ID: {welcome_channel_id}")
                
                # Убираем пользователя из обработки
                self.processing_users.discard(member.id)
                return
            
            elif os.path.exists(rejected_passport_path):
                # Пользователь возвращается с отклоненным паспортом
                logger.info(f"Пользователь {member.id} возвращается с отклоненным паспортом")
                
                # Отправляем сообщение о необходимости повторной верификации
                verification_channel = self.bot.get_channel(verification_channel_id)
                if verification_channel:
                    embed = Embed(
                        title="⚠️ Повторная верификация",
                        description=f"Пользователь {member.mention} возвращается с ранее отклоненным паспортом.\nТребуется повторная проверка.",
                        color=Color.orange()
                    )
                    await verification_channel.send(embed=embed)
                
                # Удаляем старый отклоненный паспорт для создания нового
                os.remove(rejected_passport_path)
            
            # Проверяем существующий пустой паспорт (защита от дублирования)
            view = VerificationView(self.bot, member, member_join_event=self)
            view.setup_initial_buttons()  # Инициализируем начальные кнопки
            if await view.check_existing_passport(member):
                # Если check_existing_passport вернул True, значит пользователь уже обработан
                # (кикнут за отклоненный паспорт или у него есть пустой паспорт в процессе)
                self.processing_users.discard(member.id)
                return
                
            # Создаем эмбед для верификации
            embed = await self.create_verification_embed(member)
            
            # Создаем пустой паспорт в фоне (не блокируем основной поток)
            async def create_passport_background():
                try:
                    passport_path = await self.create_empty_passport(member)
                    # Отправляем сообщение с паспортом в канал приветствия
                    welcome_channel = self.bot.get_channel(welcome_channel_id)
                    if welcome_channel:
                        welcome_embed = Embed(
                            title="Welcome to Hordovia!",
                            description=f"Добро пожаловать на территорию Хордовии, товарищ {member.mention}!\nСлава Хордовии! Спасибо за борщ!",
                            color=Color.blue()
                        )
                        welcome_embed.set_image(url="attachment://passport.png")
                        passport_message = await welcome_channel.send(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                        view.passport_message_id = passport_message.id  # Сохраняем ID сообщения
                        logger.info(f"Создано сообщение с паспортом для {member.id}, message_id: {passport_message.id}")
                    else:
                        logger.warning(f"Не найден канал приветствия с ID: {welcome_channel_id}")
                except Exception as e:
                    logger.error(f"Ошибка при создании пустого паспорта для {member.id}: {e}")
                    view.passport_message_id = None
                finally:
                    # Убираем пользователя из обработки после завершения
                    self.processing_users.discard(member.id)
            
            # Запускаем создание паспорта в фоне
            asyncio.create_task(create_passport_background())
            
            # Отправляем сообщение с кнопками в канал верификации (это происходит сразу)
            verification_channel = self.bot.get_channel(verification_channel_id)
            if verification_channel:
                # Формируем пинг админских ролей
                admin_pings = []
                for role_id in admin_role_ids:
                    role = member.guild.get_role(role_id)
                    if role:
                        admin_pings.append(role.mention)
                
                ping_text = " ".join(admin_pings) if admin_pings else ""
                
                content = f"{ping_text}\n**Новый пользователь ожидает верификации**" if ping_text else "**Новый пользователь ожидает верификации**"
                
                verification_message = await verification_channel.send(content=content, embed=embed, view=view)
                logger.info(f"Отправлено сообщение верификации для {member.id}")
                
                # Обновляем кнопки после создания паспорта (в фоновой задаче)
                async def update_buttons_after_passport():
                    # Ждем завершения создания паспорта (максимум 30 секунд)
                    for _ in range(30):
                        if view.passport_message_id is not None:
                            break
                        await asyncio.sleep(1)
                    
                    # Обновляем кнопки с правильным passport_message_id
                    try:
                        view.setup_initial_buttons()
                        await verification_message.edit(view=view)
                        logger.info(f"Обновлены кнопки верификации для {member.id} с passport_message_id: {view.passport_message_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении кнопок верификации для {member.id}: {e}")
                
                # Запускаем обновление кнопок в фоне
                asyncio.create_task(update_buttons_after_passport())
            else:
                logger.warning(f"Не найден канал верификации с ID: {verification_channel_id}")
        
        except Exception as e:
            logger.error(f"Ошибка при обработке присоединения пользователя {member.id}: {e}")
            # Убираем пользователя из обработки при ошибке
            self.processing_users.discard(member.id)

    async def create_verification_embed(self, member):
        embed = Embed(
            title="Новый участник",
            description=f"Пользователь {member.mention} присоединился к серверу! \nПравила быстрой проверки:\n1) Аккаунт пользователя зарегистрирован не менее месяца назад\n2) Никнейм не должен содержать нецензурную лексику.\n> В противном случаи нужно переименовать по схеме ПКМ - Изменить никнейм - В поле ввода ввести ####",
            color=Color.blue()
        )
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Аккаунт создан", value=member.created_at.strftime("%d.%m.%Y"))
        return embed

    async def create_empty_passport(self, member):
        try:
            # Проверяем существование директории для шаблонов
            if not os.path.exists("images/passport_template"):
                os.makedirs("images/passport_template")
            
            # Проверяем существование необходимых файлов
            template_path = "images/passport_template/new-passport.png"
            
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Не найден файл шаблона паспорта: {template_path}")
            
            # Создаем базовый паспорт
            img = Image.open(template_path)
            draw = ImageDraw.Draw(img)
            
            # Загружаем аватарку асинхронно, но не ждем её
            avatar_task = asyncio.create_task(get_avatar(member))
            
            # Добавляем информацию на паспорт (это быстро)
            draw.text((40, img.height - 390), member.name, font=get_font(64), fill="#584a48")
            draw.text((370, img.height - 338), f"{member.created_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((370, img.height - 285), f"{member.joined_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((40, img.height - 83), f"{member.id}", font=get_font(60), fill="#584a48")
            
            # Теперь ждем аватарку (если она еще загружается)
            try:
                avatar = await asyncio.wait_for(avatar_task, timeout=3.0)  # Ждем максимум 3 секунды
                if avatar:
                    # Вставляем аватарку в паспорт
                    avatar_x = 40
                    avatar_y = 550
                    img.paste(avatar, (avatar_x, avatar_y))
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут загрузки аватарки для {member.id}")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении аватарки для {member.id}: {e}")
            
            # Сохраняем результат
            passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}_empty.png")
            img.save(passport_path, optimize=True)  # Оптимизируем сохранение
            return passport_path
        except Exception as e:
            logger.error(f"Ошибка при создании пустого паспорта: {e}")
            raise

def setup(bot: Bot):
    bot.add_cog(MemberJoinEvent(bot)) 