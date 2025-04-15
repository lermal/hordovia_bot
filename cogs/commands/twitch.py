from config import *
from bot import Bot
from nextcord import Interaction, Embed, Color, slash_command, ui, SelectOption, TextInputStyle, ButtonStyle
from nextcord.ext.commands import Cog
import json
import os
import asyncio

class AddStreamerModal(ui.Modal):
    def __init__(self, callback):
        super().__init__(title="Добавить стримера")
        self.callback_func = callback
        self.login = ui.TextInput(label="Логин стримера", required=True, max_length=50)
        self.description = ui.TextInput(label="Описание", required=False, max_length=200)
        self.add_item(self.login)
        self.add_item(self.description)
    async def callback(self, interaction: Interaction):
        login = self.login.value.strip().lower()
        description = self.description.value.strip()
        await self.callback_func(interaction, login, description)

class EditDescriptionModal(ui.Modal):
    def __init__(self, streamer, current_description, callback):
        super().__init__(title=f"Редактировать описание: {streamer}")
        self.streamer = streamer
        self.callback_func = callback
        self.description = ui.TextInput(
            label="Новое описание",
            style=TextInputStyle.paragraph,
            default_value=current_description,
            required=False,
            max_length=200
        )
        self.add_item(self.description)
    async def callback(self, interaction: Interaction):
        new_description = self.description.value
        await self.callback_func(interaction, self.streamer, new_description)

# View только с выпадающим списком (начальное состояние)
class SelectStreamerView(ui.View):
    def __init__(self, cog, streamers):
        super().__init__(timeout=180)
        self.cog = cog
        self.streamers = streamers
        
        # Создаем options для выпадающего списка
        options = []
        
        # Добавляем существующих стримеров в список
        for login, data in streamers.items():
            options.append(SelectOption(
                label=login, 
                description=data.get("description", "")[:50],
                value=login
            ))
        
        # Добавляем опцию для добавления нового стримера
        options.append(SelectOption(
            label="➕ Добавить нового стримера",
            value="add_new_streamer",
            description="Добавить нового стримера в список отслеживания"
        ))
            
        # Создаем выпадающий список
        self.select = ui.Select(
            placeholder="Выберите стримера для редактирования...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
            
    async def on_select(self, interaction: Interaction):
        selected = self.select.values[0]
        
        # Если выбрано добавление нового стримера
        if selected == "add_new_streamer":
            await interaction.response.send_modal(AddStreamerModal(self.cog.add_streamer_callback))
            return
            
        # Иначе создаем view с действиями для выбранного стримера
        view = StreamerActionsView(self.cog, self.streamers, selected)
        embed = await self.cog.create_twitch_list_embed(selected)
        await interaction.response.edit_message(embed=embed, view=view)

# View с кнопками для взаимодействия с выбранным стримером
class StreamerActionsView(ui.View):
    def __init__(self, cog, streamers, selected):
        super().__init__(timeout=180)
        self.cog = cog
        self.streamers = streamers
        self.selected = selected
        
        # Создаем выпадающий список с действиями
        actions_select = ui.Select(
            placeholder="Выберите действие...",
            options=[
                SelectOption(label="◀️ Вернуться к списку", value="back", description="Вернуться к полному списку стримеров"),
                SelectOption(label="✏️ Изменить описание", value="edit", description="Изменить описание стримера"),
                SelectOption(label="🔄 Вкл/Выкл уведомления", value="toggle", description="Включить/выключить уведомления"),
                SelectOption(label="🗑️ Удалить стримера", value="delete", description="Удалить стримера из списка")
            ]
        )
        actions_select.callback = self.on_action_select
        self.add_item(actions_select)
        
    async def on_action_select(self, interaction: Interaction):
        action = interaction.data["values"][0]
        
        if action == "back":
            # Возвращаемся к обычному списку стримеров
            view = SelectStreamerView(self.cog, self.streamers)
            embed = await self.cog.create_twitch_list_embed()
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif action == "edit":
            # Открываем модальное окно для редактирования описания
            current_description = self.streamers[self.selected].get("description", "")
            await interaction.response.send_modal(
                EditDescriptionModal(self.selected, current_description, self.cog.edit_description_callback)
            )
            
        elif action == "toggle":
            # Включаем/выключаем уведомления
            await self.cog.toggle_streamer_callback(interaction, self.selected)
            
        elif action == "delete":
            # Удаляем стримера
            await self.cog.delete_streamer_callback(interaction, self.selected)

class TwitchCommands(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.streamers_file = "data/streamers.json"
        self.avatar_cache = {}
        self.load_streamers()
        self.load_avatar_cache()
        
    def load_streamers(self):
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(self.streamers_file):
            with open(self.streamers_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        with open(self.streamers_file, "r", encoding="utf-8") as f:
            self.streamers = json.load(f)
            
    def save_streamers(self):
        with open(self.streamers_file, "w", encoding="utf-8") as f:
            json.dump(self.streamers, f, ensure_ascii=False, indent=4)
            
    def load_avatar_cache(self):
        path = "data/avatar_cache.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.avatar_cache = json.load(f)
            except Exception as e:
                print(f"Twitch: Ошибка при загрузке кэша аватарок: {e}")
                self.avatar_cache = {}
                
    def save_avatar_cache(self):
        path = "data/avatar_cache.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.avatar_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Twitch: Ошибка при сохранении кэша аватарок: {e}")
            
    async def get_user_avatar(self, login):
        """Получить URL аватарки стримера по логину с кэшированием"""
        if login in self.avatar_cache:
            return self.avatar_cache[login]
        try:
            from cogs.events.twitch_stream import TwitchStream
            twitch_cog = self.bot.get_cog("TwitchStream")
            if twitch_cog and hasattr(twitch_cog, "get_user_avatar"):
                # Используем метод из класса TwitchStream, если он доступен
                avatar_url = await twitch_cog.get_user_avatar(login)
                if avatar_url:
                    self.avatar_cache[login] = avatar_url
                    self.save_avatar_cache()
                    return avatar_url
            return None
        except Exception as e:
            print(f"Twitch: Ошибка при получении аватарки: {e}")
            return None
            
    @slash_command(
        name="twitch_list",
        description="Управление стримерами Twitch через UI",
        guild_ids=GUILD_IDS
    )
    async def twitch_list(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = await self.create_twitch_list_embed()
        
        # Всегда отправляем сообщение с интерфейсом выбора
        view = SelectStreamerView(self, self.streamers)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def create_twitch_list_embed(self, selected=None):
        """Создает embed со списком стримеров или детальную информацию о выбранном стримере"""
        self.load_streamers()
        
        # Если выбран стример, показываем детальную информацию только о нём
        if selected and selected in self.streamers:
            streamer_data = self.streamers[selected]
            status = "Включен ✅" if streamer_data["enabled"] else "Выключен ❌"
            
            embed = Embed(
                title=f"📺 Стример: {selected}",
                description=f"{streamer_data.get('description', 'Нет описания')}",
                color=Color.purple()
            )
            
            embed.add_field(name="Статус уведомлений", value=status, inline=True)
            embed.add_field(name="Канал", value=f"[Twitch.tv/{selected}](https://twitch.tv/{selected})", inline=True)
            
            # Получаем и устанавливаем аватарку
            avatar_url = await self.get_user_avatar(selected)
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
                
            return embed
        
        # Иначе показываем список всех стримеров
        embed = Embed(
            title="📺 Список стримеров Twitch",
            description="Стримеры, для которых настроены уведомления:",
            color=Color.blue()
        )
        
        if not self.streamers:
            embed.add_field(
                name="Нет стримеров", 
                value="Используйте команду `/twitch_list` для добавления стримеров", 
                inline=False
            )
            return embed
            
        for channel, data in self.streamers.items():
            status = "Включен" if data["enabled"] else "Выключен"
            
            name = f"@{channel} | {status}"
            embed.add_field(
                name=name,
                value=f"Описание: {data['description']}",
                inline=False
            )
            
        return embed
            
    async def add_streamer_callback(self, interaction: Interaction, login, description):
        self.load_streamers()
        
        if login in self.streamers:
            await interaction.response.send_message(f"❌ Стример **{login}** уже есть в списке.", ephemeral=True)
            return
            
        self.streamers[login] = {"description": description or f"Стрим {login}", "enabled": True}
        self.save_streamers()
        
        # Создаем обновленный интерфейс с уведомлением в footer
        embed = await self.create_twitch_list_embed(selected=login)
        embed.set_footer(text=f"✅ Стример {login} успешно добавлен!")
        view = StreamerActionsView(self, self.streamers, selected=login)
        
        # Отвечаем на взаимодействие редактированием сообщения
        await interaction.response.edit_message(embed=embed, view=view)
        
        # Запускаем таймер для удаления уведомления через 3 секунды
        self.bot.loop.create_task(self.remove_notification_after_delay(interaction, login))
            
    async def delete_streamer_callback(self, interaction: Interaction, login):
        self.load_streamers()
        
        if login not in self.streamers:
            await interaction.response.send_message(f"❌ Стример **{login}** не найден.", ephemeral=True)
            return
            
        # Удаляем стримера
        del self.streamers[login]
        self.save_streamers()
        
        # Возвращаемся к обычному списку
        view = SelectStreamerView(self, self.streamers)
        embed = await self.create_twitch_list_embed()
        
        # Сразу отвечаем редактированием
        await interaction.response.edit_message(embed=embed, view=view)
        
    async def toggle_streamer_callback(self, interaction: Interaction, login):
        self.load_streamers()
        
        if login not in self.streamers:
            await interaction.response.send_message(f"❌ Стример **{login}** не найден.", ephemeral=True)
            return
            
        # Меняем статус
        self.streamers[login]["enabled"] = not self.streamers[login]["enabled"]
        self.save_streamers()
        
        # Получаем новый статус для сообщения
        status = "включены" if self.streamers[login]["enabled"] else "выключены"
        
        # Обновляем с тем же view
        view = StreamerActionsView(self, self.streamers, login)
        embed = await self.create_twitch_list_embed(selected=login)
        
        # Отвечаем
        await interaction.response.edit_message(embed=embed, view=view)
            
    async def edit_description_callback(self, interaction: Interaction, streamer, new_description):
        self.load_streamers()
        
        # Проверяем есть ли стример в списке
        if streamer not in self.streamers:
            await interaction.response.send_message(f"❌ Стример **{streamer}** не найден.", ephemeral=True)
            return
            
        # Обновляем описание
        self.streamers[streamer]["description"] = new_description
        self.save_streamers()
        
        # Создаем обновленный интерфейс с уведомлением в footer
        embed = await self.create_twitch_list_embed(selected=streamer)
        embed.set_footer(text=f"✅ Описание для {streamer} успешно обновлено!")
        view = StreamerActionsView(self, self.streamers, selected=streamer)
        
        # Отвечаем на взаимодействие редактированием сообщения
        await interaction.response.edit_message(embed=embed, view=view)
        
        # Запускаем таймер для удаления уведомления через 3 секунды
        self.bot.loop.create_task(self.remove_notification_after_delay(interaction, streamer))

    async def remove_notification_after_delay(self, interaction, streamer, delay=3):
        """Удаляет уведомление об успешном обновлении через заданное время"""
        await asyncio.sleep(delay)
        try:
            # Получаем оригинальное сообщение
            message = await interaction.original_message()
            if message:
                # Обновляем embed без уведомления
                embed = await self.create_twitch_list_embed(selected=streamer)
                view = StreamerActionsView(self, self.streamers, selected=streamer)
                await message.edit(embed=embed, view=view)
        except Exception as e:
            print(f"Не удалось удалить уведомление: {e}")

def setup(bot: Bot):
    bot.add_cog(TwitchCommands(bot)) 