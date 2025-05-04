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

from logger import setup_logger

logger = setup_logger()

# Путь к шрифту и паспортам
FONT_PATH = "fonts/ttf.ttf"
FONT_SIZE = 32
PASSPORTS_DIR = "images/passports"

def get_font(font_size=FONT_SIZE):
    try:
        return ImageFont.truetype(FONT_PATH, font_size)
    except:
        logger.error(f"Ошибка загрузки шрифта {FONT_PATH}, использую системный шрифт")
        return ImageFont.load_default()

async def get_avatar(member):
    # Получаем URL аватарки (используем формат PNG)
    avatar_url = member.display_avatar.with_format("png").url
    
    # Скачиваем аватарку
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as response:
            if response.status == 200:
                avatar_data = await response.read()
                # Преобразуем байты в изображение PIL
                avatar = Image.open(BytesIO(avatar_data))
                # Изменяем размер до 220x220
                avatar = avatar.resize((220, 220), Image.Resampling.LANCZOS)
                return avatar
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
        self.admin_role_ids = settings.get("admin_role_ids", [])
        
        self.passport_message_id = None  # ID сообщения с паспортом в канале "Добро пожаловать"
        self.is_revoke_state = False

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Проверяем, есть ли у пользователя нужные роли
        has_permission = any(role.id in self.admin_role_ids for role in interaction.user.roles)
        if not has_permission:
            await interaction.response.send_message("У вас нет прав для выполнения этого действия!", ephemeral=True)
            return False
        return True

    async def check_existing_passport(self, member):
        # Проверяем оба варианта паспорта (принятый и отклоненный)
        accept_passport = os.path.join(PASSPORTS_DIR, f"{member.id}_accept.png")
        deny_passport = os.path.join(PASSPORTS_DIR, f"{member.id}_deny.png")
        
        if os.path.exists(deny_passport):
            try:
                await member.send("Вам отказано в доступе к серверу.")
            except:
                pass
            await member.kick(reason="Ранее отклоненная заявка")
            return True
        elif os.path.exists(accept_passport):
            role = member.guild.get_role(self.member_role_id)
            if role:
                await member.add_roles(role)
            return True
        return False

    @button(label="Принять", style=ButtonStyle.green)
    async def accept(self, button: Button, interaction: Interaction):
        try:
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
                self.clear_items()
                revoke_button = Button(label="Отозвать решение", style=ButtonStyle.gray, custom_id="revoke_accept")
                revoke_button.callback = self.revoke_decision
                self.add_item(revoke_button)
                self.is_revoke_state = True
                
                # Обновляем сообщение
                embed = Embed(
                    title="Участник принят",
                    description=f"Пользователь {self.member.mention} успешно принят на сервер!",
                    color=Color.green()
                )
                embed.add_field(name="ID", value=self.member.id)
                embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
                
                await interaction.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"Участник {self.member.mention} принят!", ephemeral=True)
                
                # Обновляем сообщение с паспортом в канале приветствия
                welcome_channel = self.bot.get_channel(1356017783946874920)
                if welcome_channel and self.passport_message_id:
                    try:
                        passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                        welcome_embed = Embed(
                            title="Welcome to Hordovia!",
                            description=f"Добро пожаловать на территорию Хордовии, товарищ {self.member.mention}!\nДежурный {interaction.user.mention} проверил твою заявку.\nСлава Хордовии! Спасибо за борщ!",
                            color=Color.green()
                        )
                        welcome_embed.set_image(url="attachment://passport.png")
                        await passport_message.edit(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении сообщения с паспортом: {e}")
        except Exception as e:
            logger.error(f"Ошибка в методе accept: {e}")
            await interaction.response.send_message("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)

    @button(label="Отклонить", style=ButtonStyle.red)
    async def reject(self, button: Button, interaction: Interaction):
        try:
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
            self.clear_items()
            revoke_button = Button(label="Отозвать решение", style=ButtonStyle.gray, custom_id="revoke_reject")
            revoke_button.callback = self.revoke_decision
            self.add_item(revoke_button)
            self.is_revoke_state = True
            
            # Обновляем сообщение
            embed = Embed(
                title="Участник отклонен",
                description=f"Пользователь {self.member.mention} был отклонен и кикнут с сервера.",
                color=Color.red()
            )
            embed.add_field(name="ID", value=self.member.id)
            embed.add_field(name="Аккаунт создан", value=self.member.created_at.strftime("%d.%m.%Y"))
            
            await interaction.message.edit(embed=embed, view=self)
            await interaction.response.send_message(f"Участник {self.member.mention} отклонен и кикнут.", ephemeral=True)
            
            # Обновляем сообщение с паспортом в канале приветствия
            welcome_channel = self.bot.get_channel(1356017783946874920)
            if welcome_channel and self.passport_message_id:
                try:
                    passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                    welcome_embed = Embed(
                        title="Welcome to Hordovia!",
                        description=f"Пользователь {self.member.mention} был отклонен дежурным {interaction.user.mention}.\nСлава Хордовии! Спасибо за борщ!",
                        color=Color.red()
                    )
                    welcome_embed.set_image(url="attachment://passport.png")
                    await passport_message.edit(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                except Exception as e:
                    logger.error(f"Ошибка при обновлении сообщения с паспортом: {e}")
            
            # Отправляем сообщение пользователю и кикаем его
            try:
                await self.member.send("Ваша заявка на вступление была отклонена.")
            except:
                pass
            await self.member.kick(reason="Отклонен администрацией")
        except Exception as e:
            logger.error(f"Ошибка в методе reject: {e}")
            await interaction.response.send_message("Произошла ошибка при выполнении действия. Попробуйте еще раз.", ephemeral=True)

    async def revoke_decision(self, interaction: Interaction):
        try:
            # Удаляем паспорт (проверяем оба варианта)
            accept_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_accept.png")
            deny_passport = os.path.join(PASSPORTS_DIR, f"{self.member.id}_deny.png")
            
            if os.path.exists(accept_passport):
                os.remove(accept_passport)
            if os.path.exists(deny_passport):
                os.remove(deny_passport)
            
            # Если у пользователя есть роль - забираем её
            role = interaction.guild.get_role(self.member_role_id)
            member = interaction.guild.get_member(self.member.id)
            if member and role and role in member.roles:
                await member.remove_roles(role)
            
            # Обновляем сообщение без кнопок
            embed = Embed(
                title="Решение отозвано",
                description=f"Решение по пользователю {self.member.mention} было отозвано.",
                color=Color.blue()
            )
            embed.add_field(name="ID", value=self.member.id)
            
            await interaction.message.edit(embed=embed, view=None)
            await interaction.response.send_message("Решение успешно отозвано.", ephemeral=True)
            
            # Возвращаем пустой паспорт в канал приветствия
            welcome_channel = self.bot.get_channel(1356017783946874920)
            if welcome_channel and self.passport_message_id:
                try:
                    # Создаем пустой паспорт
                    passport_path = await self.create_empty_passport(self.member)
                    passport_message = await welcome_channel.fetch_message(self.passport_message_id)
                    welcome_embed = Embed(
                        title="Welcome to Hordovia!",
                        description=f"Добро пожаловать на территорию Хордовии, товарищ {self.member.mention}!\nСлава Хордовии! Спасибо за борщ!",
                        color=Color.blue()
                    )
                    welcome_embed.set_image(url="attachment://passport.png")
                    await passport_message.edit(embed=welcome_embed, file=File(passport_path, filename="passport.png"))
                except Exception as e:
                    logger.error(f"Ошибка при обновлении сообщения с паспортом: {e}")
        except Exception as e:
            logger.error(f"Ошибка в методе revoke_decision: {e}")
            await interaction.response.send_message("Произошла ошибка при отзыве решения. Попробуйте еще раз.", ephemeral=True)

    async def create_stamped_passport(self, member, accepted: bool):
        try:
            # Проверяем существование директории для шаблонов
            if not os.path.exists("images/passport_template"):
                os.makedirs("images/passport_template")
            
            # Проверяем существование директории для паспортов
            if not os.path.exists(PASSPORTS_DIR):
                os.makedirs(PASSPORTS_DIR)
            
            # Проверяем существование необходимых файлов
            template_path = "images/passport_template/new-passport.png"
            stamp_path = "images/passport_template/press_yes.png" if accepted else "images/passport_template/press_no.png"
            
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Не найден файл шаблона паспорта: {template_path}")
            if not os.path.exists(stamp_path):
                raise FileNotFoundError(f"Не найден файл печати: {stamp_path}")
            
            # Создаем базовый паспорт
            img = Image.open(template_path)
            draw = ImageDraw.Draw(img)
            
            # Получаем и добавляем аватарку
            avatar = await get_avatar(member)
            if avatar:
                # Создаем круглую маску для аватарки
                mask = Image.new('L', (220, 220), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rectangle((0, 0, 220, 220), fill=255)
                
                # Вставляем аватарку в паспорт
                avatar_x = 40
                avatar_y = 550
                img.paste(avatar, (avatar_x, avatar_y))
            
            # Добавляем информацию на паспорт
            draw.text((40, img.height - 390), member.name, font=get_font(64), fill="#584a48")
            draw.text((370, img.height - 338), f"{member.created_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((370, img.height - 245), f"{member.joined_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((40, img.height - 83), f"{member.id}", font=get_font(60), fill="#584a48")
            
            # Добавляем печать
            stamp_img = Image.open(stamp_path)
            
            # Добавляем дату на печать
            stamp_draw = ImageDraw.Draw(stamp_img)
            current_date = datetime.now().strftime("%d %B, %Y")
            stamp_font = ImageFont.truetype(FONT_PATH, 48)
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
            
            # Сохраняем результат
            suffix = "_accept" if accepted else "_deny"
            passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}{suffix}.png")
            img.save(passport_path)
            return passport_path
        except Exception as e:
            logger.error(f"Ошибка при создании паспорта: {e}")
            raise

class MemberJoinEvent(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.settings_manager = SettingsManager()
        
        # Создаем директорию для паспортов, если её нет
        if not os.path.exists(PASSPORTS_DIR):
            os.makedirs(PASSPORTS_DIR)

    @Cog.listener()
    async def on_member_join(self, member):
        # Получаем настройки верификации
        settings = self.settings_manager.get_all_settings().get("verification", {})
        welcome_channel_id = settings.get("welcome_channel_id", 0)
        verification_channel_id = settings.get("verification_channel_id", 0)
        
        # Проверяем существующий паспорт
        view = VerificationView(self.bot, member)
        if await view.check_existing_passport(member):
            return
            
        # Создаем эмбед
        embed = await self.create_verification_embed(member)
        
        # Создаем пустой паспорт
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
        except Exception as e:
            logger.error(f"Ошибка при создании пустого паспорта: {e}")
        
        # Отправляем сообщение с кнопками в канал верификации
        verification_channel = self.bot.get_channel(verification_channel_id)
        if verification_channel:
            await verification_channel.send(embed=embed, view=view)

    async def create_verification_embed(self, member):
        embed = Embed(
            title="Новый участник",
            description=f"Пользователь {member.mention} присоединился к серверу",
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
            
            # Получаем и добавляем аватарку
            avatar = await get_avatar(member)
            if avatar:
                # Создаем круглую маску для аватарки
                mask = Image.new('L', (220, 220), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rectangle((0, 0, 220, 220), fill=255)
                
                # Вставляем аватарку в паспорт
                avatar_x = 40
                avatar_y = 550
                img.paste(avatar, (avatar_x, avatar_y))
            
            # Добавляем информацию на паспорт
            draw.text((40, img.height - 390), member.name, font=get_font(64), fill="#584a48")
            draw.text((370, img.height - 338), f"{member.created_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((370, img.height - 245), f"{member.joined_at.strftime('%d %B, %Y')}", font=get_font(48), fill="#584a48")
            draw.text((40, img.height - 83), f"{member.id}", font=get_font(60), fill="#584a48")
            
            # Сохраняем результат
            passport_path = os.path.join(PASSPORTS_DIR, f"{member.id}_empty.png")
            img.save(passport_path)
            return passport_path
        except Exception as e:
            logger.error(f"Ошибка при создании пустого паспорта: {e}")
            raise

def setup(bot: Bot):
    bot.add_cog(MemberJoinEvent(bot)) 