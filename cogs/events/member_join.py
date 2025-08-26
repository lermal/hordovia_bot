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
    def __init__(self, bot: Bot, member, timeout: int = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.member = member
        self.settings_manager = SettingsManager()
        
        # Получаем настройки верификации
        settings = self.settings_manager.get_all_settings().get("verification", {})
        self.member_role_id = settings.get("member_role_id", 0)
        self.admin_role_ids = normalize_admin_role_ids(settings.get("admin_role_ids", []))
        
        self.passport_message_id = None  # ID сообщения с паспортом в канале "Добро пожаловать"
        self.is_revoke_state = False
        
        # Создаем начальные кнопки
        self.setup_initial_buttons()

    def setup_initial_buttons(self):
        """Создает начальные кнопки Принять/Отклонить"""
        self.clear_items()
        
        # Кнопка "Принять"
        accept_btn = Button(label="Принять", style=ButtonStyle.green)
        accept_btn.callback = self.handle_accept
        self.add_item(accept_btn)
        
        # Кнопка "Отклонить"
        reject_btn = Button(label="Отклонить", style=ButtonStyle.red)
        reject_btn.callback = self.handle_reject
        self.add_item(reject_btn)

    def setup_revoke_button(self):
        """Создает кнопку Отозвать решение"""
        self.clear_items()
        
        revoke_btn = Button(label="Отозвать решение", style=ButtonStyle.gray)
        revoke_btn.callback = self.handle_revoke
        self.add_item(revoke_btn)
        self.is_revoke_state = True

    def setup_cancel_revoke_button(self):
        """Создает кнопку Отменить отзыв (только для отклоненных)"""
        self.clear_items()
        
        cancel_btn = Button(label="Отменить отзыв", style=ButtonStyle.secondary)
        cancel_btn.callback = self.handle_cancel_revoke
        self.add_item(cancel_btn)

    def reset_to_initial_state(self):
        """Сбрасывает View к исходному состоянию с кнопками Принять/Отклонить"""
        self.is_revoke_state = False
        self.setup_initial_buttons()

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Обновляем настройки перед проверкой (на случай, если они изменились)
        settings = self.settings_manager.get_all_settings().get("verification", {})
        admin_role_ids = settings.get("admin_role_ids", [])
        
        # Проверяем, есть ли у пользователя нужные роли
        # Обеспечиваем правильную обработку типов для admin_role_ids
        if isinstance(admin_role_ids, int):
            admin_role_ids = [admin_role_ids]
        elif isinstance(admin_role_ids, list):
            admin_role_ids = admin_role_ids
        else:
            admin_role_ids = []
        
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
        await self.accept(interaction)

    async def handle_reject(self, interaction: Interaction):
        """Обработчик кнопки Отклонить"""
        await self.reject(interaction)

    async def handle_revoke(self, interaction: Interaction):
        """Обработчик кнопки Отозвать решение"""
        await self.revoke_decision(interaction)

    async def handle_cancel_revoke(self, interaction: Interaction):
        """Обработчик кнопки Отменить отзыв"""
        await self.cancel_revoke_decision(interaction)

    async def accept(self, interaction: Interaction):
        try:
            logger.info(f"Начинаем принятие пользователя {self.member.id}, passport_message_id: {self.passport_message_id}")
            
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
                    await interaction.response.send_message("Произошла ошибка при создании паспорта. Попробуйте еще раз.", ephemeral=True)
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
                
                # Используем followup вместо response для избежания ошибки истекшего interaction
                try:
                    await interaction.response.send_message(f"Участник {self.member.mention} принят!", ephemeral=True)
                except:
                    await interaction.followup.send(f"Участник {self.member.mention} принят!", ephemeral=True)
                
                # Обновляем сообщение с паспортом в канале приветствия
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
                await interaction.response.send_message("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)
            except:
                await interaction.followup.send("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)

    async def reject(self, interaction: Interaction):
        try:
            logger.info(f"Начинаем отклонение пользователя {self.member.id}, passport_message_id: {self.passport_message_id}")
            
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
                await interaction.response.send_message("Произошла ошибка при создании паспорта. Попробуйте еще раз.", ephemeral=True)
                return
            
            # Меняем кнопки на "Отозвать решение"
            self.setup_revoke_button()
            
            # Обновляем сообщение
            embed = Embed(
                title="Участник отклонен",
                description=f"Пользователь {self.member.mention} был отклонен и кикнут с сервера.",
                color=Color.red()
            )
            embed.add_field(name="ID", value=self.member.id)
            embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
            
            await interaction.message.edit(embed=embed, view=self)
            
            # Используем followup вместо response для избежания ошибки истекшего interaction
            try:
                await interaction.response.send_message(f"Участник {self.member.mention} отклонен и кикнут.", ephemeral=True)
            except:
                await interaction.followup.send(f"Участник {self.member.mention} отклонен и кикнут.", ephemeral=True)
            
            # Обновляем сообщение с паспортом в канале приветствия
            settings = self.settings_manager.get_all_settings().get("verification", {})
            welcome_channel_id = settings.get("welcome_channel_id", 0)
            welcome_channel = self.bot.get_channel(welcome_channel_id)
            
            if welcome_channel and self.passport_message_id:
                try:
                    logger.info(f"Обновляем сообщение с паспортом для {self.member.id}, message_id: {self.passport_message_id}")
                    passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                    welcome_embed = Embed(
                        title="Welcome to Hordovia!",
                        description=f"Пользователь {self.member.mention} был отклонен дежурным {interaction.user.mention}.\nСлава Хордовии! Спасибо за борщ!",
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
            await self.member.kick(reason="Отклонен администрацией")
        except Exception as e:
            logger.error(f"Ошибка в методе reject: {e}")
            try:
                await interaction.response.send_message("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)
            except:
                await interaction.followup.send("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)

    async def revoke_decision(self, interaction: Interaction):
        try:
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
                
                try:
                    await interaction.response.send_message("Принятие пользователя отозвано. Пользователь возвращен к ожиданию верификации.", ephemeral=True)
                except:
                    await interaction.followup.send("Принятие пользователя отозвано. Пользователь возвращен к ожиданию верификации.", ephemeral=True)
            
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
                    await interaction.response.send_message("Отклонение пользователя отозвано. Пользователь уведомлен в ЛС.", ephemeral=True)
                except:
                    await interaction.followup.send("Отклонение пользователя отозвано. Пользователь уведомлен в ЛС.", ephemeral=True)
            
            else:
                # Неизвестное состояние
                logger.warning(f"Попытка отозвать решение для пользователя {self.member.id}, но паспорт не найден")
                try:
                    await interaction.response.send_message("Не найден паспорт для отзыва решения.", ephemeral=True)
                except:
                    await interaction.followup.send("Не найден паспорт для отзыва решения.", ephemeral=True)
                    
        except Exception as e:
            logger.error(f"Ошибка в методе revoke_decision: {e}")
            try:
                await interaction.response.send_message("Произошла ошибка при отзыве решения. Попробуйте еще раз.", ephemeral=True)
            except:
                await interaction.followup.send("Произошла ошибка при отзыве решения. Попробуйте еще раз.", ephemeral=True)

    async def cancel_revoke_decision(self, interaction: Interaction):
        """Отменяет отзыв (удаляет сообщение) - только для отклоненных пользователей"""
        try:
            # Удаляем сообщение верификации
            await interaction.message.delete()
            logger.info(f"Удалено сообщение верификации для пользователя {self.member.id} по запросу отмены отзыва")
            
            try:
                await interaction.response.send_message("Сообщение верификации удалено.", ephemeral=True)
            except:
                # Если сообщение уже удалено, interaction может не сработать
                pass
                
        except Exception as e:
            logger.error(f"Ошибка в методе cancel_revoke_decision: {e}")
            try:
                await interaction.response.send_message("Произошла ошибка при удалении сообщения.", ephemeral=True)
            except:
                await interaction.followup.send("Произошла ошибка при удалении сообщения.", ephemeral=True)

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
        
        # Получаем настройки верификации
        settings = self.settings_manager.get_all_settings().get("verification", {})
        self.admin_role_ids = normalize_admin_role_ids(settings.get("admin_role_ids", []))
        
        # Создаем директорию для паспортов, если её нет
        if not os.path.exists(PASSPORTS_DIR):
            os.makedirs(PASSPORTS_DIR)
        
        # Словарь для отслеживания обрабатываемых пользователей (предотвращает дублирование)
        self.processing_users = set()

    @Cog.listener()
    async def on_member_join(self, member):
        # Проверяем, не обрабатывается ли уже этот пользователь
        if member.id in self.processing_users:
            logger.warning(f"Пользователь {member.id} уже обрабатывается, пропускаем")
            return
        
        try:
            # Добавляем пользователя в обработку
            self.processing_users.add(member.id)
            
            # Обновляем настройки верификации (на случай, если они изменились)
            settings = self.settings_manager.get_all_settings().get("verification", {})
            self.admin_role_ids = normalize_admin_role_ids(settings.get("admin_role_ids", []))
            
            welcome_channel_id = settings.get("welcome_channel_id", 0)
            verification_channel_id = settings.get("verification_channel_id", 0)
            member_role_id = settings.get("member_role_id", 0)
            
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
            view = VerificationView(self.bot, member)
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
                for role_id in self.admin_role_ids:
                    role = member.guild.get_role(role_id)
                    if role:
                        admin_pings.append(role.mention)
                
                ping_text = " ".join(admin_pings) if admin_pings else ""
                
                content = f"{ping_text}\n**Новый пользователь ожидает верификации**" if ping_text else "**Новый пользователь ожидает верификации**"
                
                await verification_channel.send(content=content, embed=embed, view=view)
                logger.info(f"Отправлено сообщение верификации для {member.id}")
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