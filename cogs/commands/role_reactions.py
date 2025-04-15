from config import *
from bot import Bot
from nextcord import (
    Interaction, 
    Embed, 
    Color, 
    slash_command, 
    ui, 
    Role, 
    TextChannel, 
    Message, 
    Permissions,
    ButtonStyle,
    SelectOption,
    TextInputStyle
)
from nextcord.ext.commands import Cog
import json
import asyncio

# Модальное окно для ввода ID сообщения
class AddMessageModal(ui.Modal):
    def __init__(self, callback):
        super().__init__(title="Добавить сообщение")
        self.callback_func = callback
        
        self.message_id = ui.TextInput(
            label="ID сообщения", 
            placeholder="Введите ID сообщения для настройки",
            required=True,
            max_length=20
        )
        
        self.add_item(self.message_id)
        
    async def callback(self, interaction: Interaction):
        try:
            message_id = int(self.message_id.value.strip())
            await self.callback_func(interaction, message_id)
        except ValueError:
            await interaction.response.send_message("❌ ID сообщения должен быть числом", ephemeral=True)

# Модальное окно для добавления роли-реакции
class AddReactionRoleModal(ui.Modal):
    def __init__(self, callback, message_id):
        super().__init__(title="Добавить роль-реакцию")
        self.callback_func = callback
        self.message_id = message_id
        
        self.emoji = ui.TextInput(
            label="Эмодзи", 
            placeholder="Введите эмодзи (например: 👍 или :thumbsup:)",
            required=True, 
            max_length=20
        )
        
        self.role_id = ui.TextInput(
            label="ID роли", 
            placeholder="Введите ID роли",
            required=True, 
            max_length=20
        )
        
        self.add_item(self.emoji)
        self.add_item(self.role_id)
        
    async def callback(self, interaction: Interaction):
        emoji = self.emoji.value.strip()
        try:
            role_id = int(self.role_id.value.strip())
            await self.callback_func(interaction, self.message_id, emoji, role_id)
        except ValueError:
            await interaction.response.send_message("❌ ID роли должен быть числом", ephemeral=True)

# Главное меню выбора сообщения
class MessageSelectView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog
        
        # Важно получить свежую копию кэша для инициализации
        self.update_message_select()
        
    def update_message_select(self):
        # Удаляем предыдущий селект, если он есть
        for item in self.children[:]:
            if isinstance(item, ui.Select):
                self.remove_item(item)
                
        # Получаем все уникальные сообщения с реакциями
        message_groups = {}
        
        # Важно получить свежую копию кэша сообщений
        message_cache = self.cog.message_cache.copy()
        for message_id, channel_id in message_cache.items():
            message_groups[message_id] = channel_id
            
        # Создаем опции для выпадающего списка
        options = []
        
        # Добавляем опцию добавления нового сообщения
        options.append(SelectOption(
            label="➕ Добавить новое сообщение",
            value="add_new_message",
            description="Настроить ролевые реакции для нового сообщения"
        ))
        
        # Добавляем существующие сообщения
        for msg_id, channel_id in message_groups.items():
            options.append(SelectOption(
                label=f"ID: {msg_id}",
                description=f"Канал: {channel_id}",
                value=str(msg_id)
            ))
        
        # Создаем выпадающий список
        self.select = ui.Select(
            placeholder="Выберите сообщение или добавьте новое...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: Interaction):
        selected = self.select.values[0]
        
        # Если выбрана опция добавления нового сообщения
        if selected == "add_new_message":
            # Отправляем модальное окно для добавления сообщения
            await interaction.response.send_modal(
                AddMessageModal(self.cog.add_message_callback)
            )
            
            # Через 1 секунду обновляем интерфейс, чтобы сбросить выбор
            # Это позволит пользователю снова выбрать эту опцию, если он отменит ввод
            await asyncio.sleep(1)
            try:
                # Получаем исходное сообщение
                original_message = await interaction.original_message()
                
                # Создаем новый view с обновленным списком
                view = MessageSelectView(self.cog)
                
                # Обновляем сообщение
                await original_message.edit(view=view)
            except Exception as e:
                print(f"Не удалось обновить интерфейс: {e}")
                
            return
        
        # Если выбрано существующее сообщение
        message_id = int(selected)
        await self.cog.show_message_reactions(interaction, message_id)

# Меню управления реакциями для конкретного сообщения
class MessageActionsView(ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.message_id = message_id
        
        # Добавляем выпадающий список с действиями
        self.action_select = ui.Select(
            placeholder="Выберите действие...",
            options=[
                SelectOption(
                    label="◀️ Назад к списку сообщений", 
                    value="back_to_list",
                    description="Вернуться к списку сообщений"
                ),
                SelectOption(
                    label="➕ Добавить реакцию", 
                    value="add_reaction",
                    description="Добавить новую роль-реакцию"
                ),
                SelectOption(
                    label="✏️ Изменить реакцию", 
                    value="edit_reaction",
                    description="Изменить роль у существующей реакции"
                ),
                SelectOption(
                    label="🗑️ Удалить реакцию", 
                    value="remove_reaction",
                    description="Удалить существующую роль-реакцию"
                ),
                SelectOption(
                    label="❌ Удалить привязку к сообщению", 
                    value="delete_message",
                    description="Удалить все реакции этого сообщения"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.action_select.callback = self.on_action_select
        self.add_item(self.action_select)
    
    async def on_action_select(self, interaction: Interaction):
        action = self.action_select.values[0]
        
        if action == "back_to_list":
            # Возвращаемся к списку сообщений
            view = MessageSelectView(self.cog)
            embed = Embed(
                title="Управление ролевыми реакциями",
                description="Выберите сообщение для настройки или добавьте новое",
                color=Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif action == "add_reaction":
            # Открываем модальное окно для добавления реакции
            await interaction.response.send_modal(
                AddReactionRoleModal(self.cog.add_reaction_role_callback, self.message_id)
            )
            
        elif action == "edit_reaction":
            # Получаем список реакций для этого сообщения
            reactions = await self.cog.bot.db.get_message_role_reactions(self.message_id)
            
            if not reactions:
                await interaction.response.send_message("❌ У этого сообщения нет настроенных реакций", ephemeral=True)
                return
            
            # Создаем выпадающий список для выбора реакции
            options = []
            for r in reactions:
                role = interaction.guild.get_role(r[5])
                role_name = role.name if role else "Роль не найдена"
                options.append(SelectOption(
                    label=f"{r[4]} → {role_name}",
                    value=f"{r[4]}:{r[5]}",
                ))
            
            # Добавляем опцию отмены в начало списка
            options.insert(0, SelectOption(
                label="↩️ Отмена",
                value="cancel",
                description="Вернуться назад"
            ))
            
            # Создаем view с выпадающим списком реакций
            view = EditReactionView(self.cog, self.message_id)
            view.update_reaction_select(options)
            
            # Обновляем сообщение с интерфейсом
            embed = await self.cog.create_message_info_embed(interaction.guild, self.message_id)
            embed.add_field(
                name="Выберите реакцию для изменения",
                value="Выберите реакцию из списка ниже",
                inline=False
            )
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif action == "remove_reaction":
            # Получаем список реакций для этого сообщения
            reactions = await self.cog.bot.db.get_message_role_reactions(self.message_id)
            
            if not reactions:
                await interaction.response.send_message("❌ У этого сообщения нет настроенных реакций", ephemeral=True)
                return
            
            # Создаем выпадающий список для выбора реакции
            options = []
            for r in reactions:
                role = interaction.guild.get_role(r[5])
                role_name = role.name if role else "Роль не найдена"
                options.append(SelectOption(
                    label=f"{r[4]} → {role_name}",
                    value=r[4]
                ))
            
            # Обновляем view с выпадающим списком реакций
            view = RemoveReactionView(self.cog, self.message_id)
            view.update_reaction_select(options)
            
            # Обновляем сообщение с интерфейсом
            embed = await self.cog.create_message_info_embed(interaction.guild, self.message_id)
            embed.add_field(
                name="Выберите реакцию для удаления",
                value="Выберите реакцию из списка ниже",
                inline=False
            )
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif action == "delete_message":
            # Создаем выпадающий список для подтверждения
            view = ConfirmDeleteView(self.cog, self.message_id)
            
            # Обновляем сообщение
            embed = Embed(
                title="Подтверждение удаления",
                description=f"Вы уверены, что хотите удалить все реакции для сообщения ID: {self.message_id}?\n\n**Это действие нельзя отменить!**",
                color=Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=view)

# View для удаления реакции
class RemoveReactionView(ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.message_id = message_id
        
    def update_reaction_select(self, options):
        # Удаляем предыдущий селект, если он есть
        for item in self.children[:]:
            if isinstance(item, ui.Select):
                self.remove_item(item)
        
        # Добавляем опцию отмены в начало списка
        cancel_option = SelectOption(
            label="↩️ Отмена",
            value="cancel",
            description="Вернуться назад"
        )
        options.insert(0, cancel_option)
        
        # Создаем выпадающий список с реакциями
        self.reaction_select = ui.Select(
            placeholder="Выберите реакцию для удаления...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.reaction_select.callback = self.on_reaction_select
        self.add_item(self.reaction_select)
    
    async def on_reaction_select(self, interaction: Interaction):
        emoji = self.reaction_select.values[0]
        
        # Проверяем, если выбрана отмена
        if emoji == "cancel":
            await self.cog.show_message_reactions(interaction, self.message_id)
            return
        
        # Удаляем реакцию
        await self.cog.bot.db.remove_role_reaction(self.message_id, emoji)
        
        # Обновляем кэш в событийном коге
        try:
            events_cog = self.cog.bot.get_cog("RoleReactionEvents")
            if events_cog:
                await events_cog.update_cache(self.message_id, emoji, None)
        except Exception as e:
            print(f"Не удалось обновить кэш реакций: {e}")
        
        # Находим сообщение
        message = None
        try:
            # Ищем сообщение на сервере
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(self.message_id)
                    if message:
                        break
                except:
                    continue
                    
            if message:
                try:
                    # Удаляем реакцию с сообщения
                    await message.clear_reaction(emoji)
                except:
                    pass
        except:
            pass
        
        # Показываем обновленное сообщение с реакциями
        await self.cog.show_message_reactions(interaction, self.message_id)
        
        # Добавляем временное уведомление об успехе в footer
        try:
            original_message = await interaction.original_message()
            embed = original_message.embeds[0]
            embed.set_footer(text=f"✅ Реакция {emoji} успешно удалена")
            await original_message.edit(embed=embed)
            
            # Убираем уведомление через 3 секунды
            await asyncio.sleep(3)
            embed.set_footer(text="")
            await original_message.edit(embed=embed)
        except Exception as e:
            print(f"Ошибка при обновлении уведомления: {e}")
            pass

# View для изменения роли у реакции
class EditReactionView(ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.message_id = message_id
        
    def update_reaction_select(self, options):
        # Удаляем предыдущий селект, если он есть
        for item in self.children[:]:
            if isinstance(item, ui.Select):
                self.remove_item(item)
        
        # Создаем выпадающий список с реакциями
        self.reaction_select = ui.Select(
            placeholder="Выберите реакцию для изменения...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.reaction_select.callback = self.on_reaction_select
        self.add_item(self.reaction_select)
    
    async def on_reaction_select(self, interaction: Interaction):
        value = self.reaction_select.values[0]
        
        # Проверяем, если выбрана отмена
        if value == "cancel":
            await self.cog.show_message_reactions(interaction, self.message_id)
            return
        
        # Разбираем emoji и role_id из значения
        emoji, current_role_id = value.split(":")
        current_role_id = int(current_role_id)
        
        # Открываем модальное окно для ввода новой роли
        await interaction.response.send_modal(
            EditRoleModal(self.cog.edit_role_callback, self.message_id, emoji, current_role_id)
        )

# View для подтверждения удаления сообщения
class ConfirmDeleteView(ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        
        # Создаем выпадающий список для подтверждения
        self.confirm_select = ui.Select(
            placeholder="Подтвердите удаление...",
            options=[
                SelectOption(
                    label="↩️ Отмена",
                    value="cancel",
                    description="Вернуться назад"
                ),
                SelectOption(
                    label="⚠️ Да, удалить все реакции",
                    value="confirm",
                    description="Удалить все реакции этого сообщения"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.confirm_select.callback = self.on_confirm_select
        self.add_item(self.confirm_select)
    
    async def on_confirm_select(self, interaction: Interaction):
        action = self.confirm_select.values[0]
        
        if action == "cancel":
            # Возвращаемся к управлению сообщением
            await self.cog.show_message_reactions(interaction, self.message_id)
        elif action == "confirm":
            # Логируем состояние кэша до удаления
            print(f"Кэш до удаления: {self.cog.message_cache}")
            print(f"Удаляемое сообщение ID: {self.message_id}")
            
            # Удаляем все реакции для этого сообщения
            await self.cog.delete_message_reactions(interaction, self.message_id)
            
            # Обновляем кэш сообщений в коге
            if self.message_id in self.cog.message_cache:
                print(f"Удаляем сообщение {self.message_id} из кэша")
                del self.cog.message_cache[self.message_id]
            else:
                print(f"Сообщение {self.message_id} не найдено в кэше")
                
            # Логируем состояние кэша после удаления
            print(f"Кэш после удаления: {self.cog.message_cache}")
            
            # Возвращаемся к списку сообщений с обновленным интерфейсом
            view = MessageSelectView(self.cog)
            embed = Embed(
                title="Управление ролевыми реакциями",
                description="Выберите сообщение для настройки или добавьте новое",
                color=Color.blue()
            )
            embed.set_footer(text=f"✅ Сообщение ID: {self.message_id} успешно удалено из списка")
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Убираем уведомление через 3 секунды
            await asyncio.sleep(3)
            embed.set_footer(text="")
            try:
                original_message = await interaction.original_message()
                await original_message.edit(embed=embed)
            except Exception as e:
                print(f"Ошибка при обновлении сообщения: {e}")
                pass

# View для изменения роли у реакции
class EditRoleModal(ui.Modal):
    def __init__(self, callback, message_id, emoji, current_role_id):
        super().__init__(title=f"Изменить роль для реакции {emoji}")
        self.callback_func = callback
        self.message_id = message_id
        self.emoji = emoji
        self.current_role_id = current_role_id
        
        self.role_id = ui.TextInput(
            label="ID новой роли", 
            placeholder=f"Текущая роль: {current_role_id}",
            required=True, 
            max_length=20
        )
        
        self.add_item(self.role_id)
        
    async def callback(self, interaction: Interaction):
        try:
            new_role_id = int(self.role_id.value.strip())
            await self.callback_func(interaction, self.message_id, self.emoji, new_role_id, self.current_role_id)
        except ValueError:
            await interaction.response.send_message("❌ ID роли должен быть числом", ephemeral=True)

class RoleReactionsCommands(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.message_cache = {}  # {message_id: channel_id}
        self.bot.loop.create_task(self.load_message_cache())
    
    async def load_message_cache(self):
        """Загружает все сообщения с реакциями в кэш"""
        await self.bot.wait_until_ready()
        
        # Ждем, пока база данных будет инициализирована
        while not self.bot.db.conn:
            await asyncio.sleep(1)
            print("Ожидание инициализации БД...")
            
        try:
            reactions = await self.bot.db.get_all_role_reactions()
            
            for reaction in reactions:
                message_id = reaction[3]
                channel_id = reaction[2]
                
                self.message_cache[message_id] = channel_id
                
            print(f"Загружено {len(self.message_cache)} сообщений с реакциями")
        except Exception as e:
            print(f"Ошибка при загрузке сообщений с реакциями: {e}")
    
    @slash_command(
        name="role_reaction",
        description="Управление ролевыми реакциями",
        guild_ids=GUILD_IDS,
        default_member_permissions=Permissions(administrator=True)
    )
    async def role_reaction(self, interaction: Interaction):
        pass # Этот метод не будет вызван, так как есть подкоманды
    
    @role_reaction.subcommand(
        name="list",
        description="Управление ролевыми реакциями"
    )
    async def list_role_reactions(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        embed = Embed(
            title="Управление ролевыми реакциями",
            description="Выберите сообщение для настройки или добавьте новое",
            color=Color.blue()
        )
        
        view = MessageSelectView(self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def create_message_info_embed(self, guild, message_id):
        """Создает embed с информацией о сообщении и его реакциях"""
        # Получаем информацию о сообщении
        channel_id = self.message_cache.get(message_id)
        channel_mention = f"<#{channel_id}>" if channel_id else "Неизвестно"
        
        embed = Embed(
            title="Управление ролевыми реакциями",
            description=f"**Сообщение ID:** {message_id}\n**Канал:** {channel_mention}",
            color=Color.blue()
        )
        
        # Получаем реакции для этого сообщения
        reactions = await self.bot.db.get_message_role_reactions(message_id)
        
        # Добавляем информацию о реакциях
        if reactions:
            reaction_text = ""
            for r in reactions:
                role = guild.get_role(r[5])
                role_name = role.name if role else "Роль не найдена"
                reaction_text += f"{r[4]} → <@&{r[5]}> ({role_name})\n"
            embed.add_field(name="Настроенные реакции", value=reaction_text, inline=False)
        else:
            embed.add_field(name="Настроенные реакции", value="Нет настроенных реакций", inline=False)
        
        return embed
    
    async def show_message_reactions(self, interaction: Interaction, message_id):
        """Показывает меню управления реакциями для выбранного сообщения"""
        embed = await self.create_message_info_embed(interaction.guild, message_id)
        view = MessageActionsView(self, message_id)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def add_message_callback(self, interaction: Interaction, message_id: int):
        """Обработчик добавления нового сообщения"""
        # Проверяем, существует ли сообщение
        message = None
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(message_id)
                if message:
                    break
            except:
                continue
        
        if not message:
            await interaction.response.send_message("❌ Сообщение с указанным ID не найдено на сервере", ephemeral=True)
            return
        
        # Добавляем сообщение в кэш
        self.message_cache[message_id] = message.channel.id
        
        # Показываем меню управления реакциями
        await self.show_message_reactions(interaction, message_id)
    
    async def add_reaction_role_callback(self, interaction: Interaction, message_id: int, emoji: str, role_id: int):
        """Обработчик добавления роли-реакции"""
        # Проверяем, существует ли роль
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(f"❌ Роль с ID {role_id} не найдена", ephemeral=True)
            return
        
        # Ищем сообщение
        message = None
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(message_id)
                if message:
                    break
            except:
                continue
        
        if not message:
            await interaction.response.send_message("❌ Сообщение не найдено", ephemeral=True)
            return
        
        # Добавляем реакцию в базу данных
        success = await self.bot.db.add_role_reaction(
            interaction.guild.id, 
            message.channel.id, 
            message_id, 
            emoji, 
            role_id
        )
        
        if not success:
            await interaction.response.send_message(f"❌ Реакция {emoji} уже привязана к этому сообщению", ephemeral=True)
            return
        
        # Добавляем реакцию к сообщению
        try:
            await message.add_reaction(emoji)
        except:
            await interaction.response.send_message(f"✅ Роль добавлена, но не удалось добавить реакцию {emoji}. Убедитесь, что это действительный эмодзи.", ephemeral=True)
            return
        
        # Обновляем кэш в событийном коге
        try:
            events_cog = self.bot.get_cog("RoleReactionEvents")
            if events_cog:
                await events_cog.update_cache(message_id, emoji, role_id)
        except Exception as e:
            print(f"Не удалось обновить кэш реакций: {e}")
        
        # Обновляем сообщение
        embed = await self.create_message_info_embed(interaction.guild, message_id)
        embed.set_footer(text=f"✅ Реакция {emoji} → {role.name} успешно добавлена!")
        view = MessageActionsView(self, message_id)
        
        # Отправляем обновленное сообщение
        await interaction.response.edit_message(embed=embed, view=view)
        
        # Убираем уведомление через 3 секунды
        await asyncio.sleep(3)
        embed.set_footer(text="")
        try:
            await interaction.original_message.edit(embed=embed)
        except:
            pass

    async def delete_message_reactions(self, interaction: Interaction, message_id: int):
        """Удаляет все реакции для указанного сообщения"""
        try:
            # Получаем все настроенные реакции для сообщения
            reactions = await self.bot.db.get_message_role_reactions(message_id)
            
            if not reactions:
                return
            
            # Находим сообщение
            message = None
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(message_id)
                    if message:
                        break
                except:
                    continue
            
            # Для каждой реакции
            for reaction in reactions:
                emoji = reaction[4]
                
                # Удаляем реакцию с сообщения Discord
                if message:
                    try:
                        await message.clear_reaction(emoji)
                    except:
                        pass
                
                # Обновляем кэш в событийном коге
                try:
                    events_cog = self.bot.get_cog("RoleReactionEvents")
                    if events_cog:
                        await events_cog.update_cache(message_id, emoji, None)
                except Exception as e:
                    print(f"Не удалось обновить кэш реакций: {e}")
            
            # Удаляем все реакции из базы данных
            await self.bot.db.remove_message_reactions(message_id)
            
            # Сообщение будет удалено из кэша в confirm_delete
            
        except Exception as e:
            print(f"Ошибка при удалении реакций сообщения: {e}")
            await interaction.response.send_message(f"❌ Ошибка при удалении сообщения: {str(e)}", ephemeral=True)
    
    async def edit_role_callback(self, interaction: Interaction, message_id: int, emoji: str, new_role_id: int, old_role_id: int):
        """Обработчик изменения роли у реакции"""
        # Проверяем, существует ли новая роль
        new_role = interaction.guild.get_role(new_role_id)
        if not new_role:
            await interaction.response.send_message(f"❌ Роль с ID {new_role_id} не найдена", ephemeral=True)
            return
        
        # Находим сообщение
        message = None
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(message_id)
                if message:
                    break
            except:
                continue
        
        if not message:
            await interaction.response.send_message("❌ Сообщение не найдено", ephemeral=True)
            return
        
        try:
            # Обновляем роль в базе данных напрямую (так как метод может быть еще не загружен)
            try:
                if hasattr(self.bot.db, "update_role_reaction"):
                    # Используем метод, если он доступен
                    await self.bot.db.update_role_reaction(message_id, emoji, new_role_id)
                else:
                    # Выполняем SQL-запрос напрямую
                    await self.bot.db.conn.execute(
                        """
                        UPDATE role_reactions 
                        SET role_id = ? 
                        WHERE message_id = ? AND emoji = ?
                        """,
                        (new_role_id, message_id, emoji)
                    )
                    await self.bot.db.conn.commit()
            except Exception as e:
                print(f"Ошибка при обновлении БД: {e}")
                await interaction.response.send_message(f"❌ Ошибка при обновлении роли в БД: {str(e)}", ephemeral=True)
                return
            
            # Обновляем кэш в событийном коге
            try:
                events_cog = self.bot.get_cog("RoleReactionEvents")
                if events_cog:
                    await events_cog.update_cache(message_id, emoji, new_role_id)
            except Exception as e:
                print(f"Не удалось обновить кэш реакций: {e}")
            
            # Получаем пользователей, у которых стоит эта реакция
            users_with_reaction = []
            for reaction in message.reactions:
                if str(reaction.emoji) == emoji:
                    async for user in reaction.users():
                        if not user.bot:
                            users_with_reaction.append(user)
                    break
            
            # Выдаем всем пользователям новую роль и забираем старую
            old_role = interaction.guild.get_role(old_role_id)
            updated_users_count = 0
            
            for user in users_with_reaction:
                member = interaction.guild.get_member(user.id)
                if member:
                    try:
                        # Забираем старую роль, если она существует
                        if old_role:
                            await member.remove_roles(old_role, reason="Обновление роли по реакции")
                        
                        # Выдаем новую роль
                        await member.add_roles(new_role, reason="Обновление роли по реакции")
                        updated_users_count += 1
                    except Exception as e:
                        print(f"Ошибка при обновлении ролей пользователя {user.id}: {e}")
            
            # Обновляем интерфейс
            embed = await self.create_message_info_embed(interaction.guild, message_id)
            embed.set_footer(text=f"✅ Роль для реакции {emoji} успешно изменена! Обновлено пользователей: {updated_users_count}")
            view = MessageActionsView(self, message_id)
            
            # Отправляем обновленное сообщение
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Убираем уведомление через 3 секунды
            await asyncio.sleep(3)
            embed.set_footer(text="")
            try:
                await interaction.original_message.edit(embed=embed)
            except:
                pass
            
        except Exception as e:
            print(f"Ошибка при изменении роли: {e}")
            await interaction.response.send_message(f"❌ Ошибка при изменении роли: {str(e)}", ephemeral=True)

def setup(bot: Bot):
    bot.add_cog(RoleReactionsCommands(bot)) 