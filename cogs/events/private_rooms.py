from nextcord.ext import commands
import nextcord
from nextcord.ui import Select, View
from database import Database
from config import GUILD_IDS

# Класс для выпадающего списка настроек канала
class ChannelSettingsDropdown(nextcord.ui.Select):
    def __init__(self, private_voice, user):
        if not private_voice or not user:
            raise ValueError("Не указаны обязательные параметры канала и пользователя")
        
        self.private_voice = private_voice
        self.user = user
        options = [
            nextcord.SelectOption(label="Изменить имя", value="rename"),
            nextcord.SelectOption(label="Установить лимит", value="limit"),
            nextcord.SelectOption(label="Назначить владельца", value="transfer_owner")
        ]
        super().__init__(placeholder="Настройки канала...", options=options)

    async def callback(self, interaction: nextcord.Interaction):
        if self.values[0] == "transfer_owner":
            transfer_view = nextcord.ui.View()
            transfer_view.add_item(DropdownOwn(self.private_voice, self.user))
            await interaction.response.send_message(
                "Выберите нового владельца комнаты:",
                view=transfer_view,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Выбрано: {self.values[0]}",
                ephemeral=True
            )

# Класс для передачи прав владельца
class DropdownOwn(nextcord.ui.Select):
    def __init__(self, private_voice, user):
        self.private_voice = private_voice
        self.user = user
        self.db = Database()
        
        selectOptions = []
        for member in private_voice.members:
            if member != user:
                selectOptions.append(nextcord.SelectOption(
                    label=member.display_name,
                    description="Нажмите, чтобы назначить владельцем комнаты",
                    value=str(member.id)
                ))
        
        super().__init__(
            placeholder="Выбрать участника",
            min_values=1,
            max_values=1,
            options=selectOptions
        )

    async def callback(self, interaction: nextcord.Interaction):
        new_owner_id = int(self.values[0])
        new_owner = interaction.guild.get_member(new_owner_id)
        
        if new_owner not in self.private_voice.members:
            return await interaction.response.send_message(
                f"{interaction.user.mention}, пользователь должен находиться в комнате!",
                ephemeral=True
            )
        
        await self.db.connect()
        
        # Получаем текущие данные о комнате
        room_data = await self.db.get_private_room(self.user.id)
        
        if room_data:
            # Обновляем права владельца в БД - меняем ownerid и perms на ID нового владельца
            await self.db.update_private_room((
                new_owner_id,  # новый ownerid
                room_data[1],  # сохраняем имя
                room_data[2],  # сохраняем лимит
                self.private_voice.id,  # ID голосового канала
                new_owner_id  # новый perms
            ))
            
            # Удаляем старую запись от прежнего владельца
            await self.db.delete_private_room_by_owner(self.user.id)
            
            # Обновляем права доступа в Discord
            await self.private_voice.set_permissions(
                self.user, 
                connect=True,  # Бывший владелец все еще может подключаться
                manage_channels=False  # Но не может управлять каналом
            )
            
            await self.private_voice.set_permissions(
                new_owner, 
                connect=True,
                manage_channels=True  # Новый владелец получает права управления
            )

            await interaction.response.send_message(
                f"Новый владелец комнаты: {new_owner.mention}!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Ошибка: информация о комнате не найдена в базе данных.",
                ephemeral=True
            )

# Класс для управления правами доступа
class PermissionSettingsDropdown(Select):
    def __init__(self, private_voice, user):
        self.private_voice = private_voice
        self.user = user
        options = [
            nextcord.SelectOption(label="Добавить участника", value="add"),
            nextcord.SelectOption(label="Забанить участника", value="ban")
        ]
        super().__init__(placeholder="Управление правами...", options=options)

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(
            f"Выбрано: {self.values[0]}", 
            ephemeral=True
        )

class Voice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.guild_data = {}

    async def init_db(self):
        await self.db.connect()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()
        
        for guild_id in GUILD_IDS:
            data = await self.db.get_guild_channels(guild_id)
            if data:
                self.guild_data[guild_id] = data
                print(f"Данные гильдии {guild_id} загружены")
            else:
                print(f"Для гильдии {guild_id} выполните /setup")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        if not self.db.conn:
            await self.db.connect()

        if member.bot:
            return

        guild_data = self.guild_data.get(member.guild.id)
        if not guild_data:
            return

        create_chan_id, category_id = guild_data

        if member.guild.id not in self.guild_data:
            data = await self.db.get_guild_channels(member.guild.id)
            if data:
                self.guild_data[member.guild.id] = data

        guild_id = member.guild.id
        channel_data = self.guild_data.get(guild_id)
        
        if not channel_data:
            return
        
        create_chan_id, category_id = channel_data

        if after.channel and after.channel.id == create_chan_id:
            await self.create_private_room(member, category_id)

        if before.channel and before.channel.id != create_chan_id:
            await self.cleanup_old_room(before.channel, create_chan_id)

    async def create_private_room(self, member: nextcord.Member, category_id: int):
        try:
            existing_room = await self.db.get_private_room(member.id)
            
            if existing_room:
                voice_id = existing_room[3]
                voice_channel = member.guild.get_channel(voice_id)
                
                if voice_channel and isinstance(voice_channel, nextcord.VoiceChannel):
                    await member.move_to(voice_channel)
                    return
                    
                await self.db.delete_private_room(voice_id)

            guild = member.guild
            category = guild.get_channel(category_id)
            
            if not category or not isinstance(category, nextcord.CategoryChannel):
                raise ValueError("Категория не найдена")

            new_channel = await guild.create_voice_channel(
                name=f"Комната {member.display_name}",
                category=category,
                overwrites={
                    guild.default_role: nextcord.PermissionOverwrite(connect=False),
                    member: nextcord.PermissionOverwrite(connect=True)
                }
            )

            # Важное изменение: передаем параметры в конструкторы
            view = View(timeout=None)
            view.add_item(ChannelSettingsDropdown(new_channel, member))
            view.add_item(PermissionSettingsDropdown(new_channel, member))

            await self.db.update_private_room((
                member.id,
                new_channel.name,
                2,
                new_channel.id,
                member.id
            ))

            await member.move_to(new_channel)
            await new_channel.send(
                f"Добро пожаловать в вашу приватную комнату, {member.mention}!",
                view=view
            )
            self.bot.logger.info(f"Создана комната для {member}")

        except Exception as e:
            self.bot.logger.error(f"Ошибка: {str(e)}")

    async def cleanup_old_room(self, channel: nextcord.VoiceChannel, create_chan_id: int):
        try:
            if channel.id == create_chan_id:
                return

            if len(channel.members) == 0:
                await self.db.delete_private_room(channel.id)
                await channel.delete()
                self.bot.logger.info(f"Удалена комната: {channel.name}")

        except nextcord.HTTPException as e:
            self.bot.logger.error(f"Ошибка удаления: {str(e)}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, deleted_channel):
        if isinstance(deleted_channel, (nextcord.VoiceChannel, nextcord.CategoryChannel)):
            guild_id = deleted_channel.guild.id
            data = await self.db.get_guild_channels(guild_id)
            
            if data and deleted_channel.id in data:
                await self.db.delete_guild_channels(guild_id)
                self.guild_data.pop(guild_id, None)
                self.bot.logger.info(f"Автосброс настроек для гильдии {guild_id}")

def setup(bot):
    bot.add_cog(Voice(bot))