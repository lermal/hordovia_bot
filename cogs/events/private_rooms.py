from nextcord.ext import commands
from database import Database
from nextcord.ui import View
from config import GUILD_IDS
import traceback
import nextcord
import asyncio

class ChannelSettingsDropdown(nextcord.ui.Select):
    def __init__(self, channel, owner):
        self.channel = channel
        self.owner = owner
        
        options = [
            nextcord.SelectOption(label="Изменить название", emoji="📝", description="Переименовать комнату"),
            nextcord.SelectOption(label="Изменить лимит", emoji="👥", description="Установить максимальное количество участников"),
            nextcord.SelectOption(label="Сменить владельца", emoji="👑", description="Передать права другому пользователю"),
            nextcord.SelectOption(label="Удалить комнату", emoji="❌", description="Удалить приватную комнату")
        ]
        
        super().__init__(
            placeholder="Настройки канала", 
            min_values=1, 
            max_values=1, 
            options=options
        )

    async def callback(self, interaction: nextcord.Interaction):
        try:
            if interaction.user != self.owner:
                return await interaction.response.send_message("❌ Только владелец может управлять настройками!", ephemeral=True)
                
            if self.values[0] == "Изменить название":
                await interaction.response.send_modal(EditName(self.channel, self.owner))
                
            elif self.values[0] == "Изменить лимит":
                await interaction.response.send_modal(EditLim(self.channel, self.owner))
                
            elif self.values[0] == "Сменить владельца":
                view = View(timeout=None)
                view.add_item(DropdownOwn(self.channel, self.owner))
                await interaction.response.send_message("Выберите нового владельца:", view=view, ephemeral=True)
                
            elif self.values[0] == "Удалить комнату":
                db = Database()
                await db.connect()
                
                confirmation_view = View(timeout=60)
                confirmation_view.add_item(ConfirmButton(self.channel, db))
                await interaction.response.send_message(
                    "⚠️ Вы уверены, что хотите удалить комнату? Это действие невозможно отменить.", 
                    view=confirmation_view, 
                    ephemeral=True
                )

            try:
                async for message in self.channel.history(limit=100):
                    if (message.author == interaction.guild.me and 
                        ((message.embeds and message.embeds[0].title == "Управление приватной комнатой"))):
                        view = View(timeout=None)
                        view.add_item(ChannelSettingsDropdown(self.channel, self.owner))
                        view.add_item(PermissionSettingsDropdown(self.channel, self.owner))
                        
                        embed = message.embeds[0]
                        await message.edit(embed=embed, view=view)
                        break

            except Exception as e:
                print(f"Ошибка при обновлении меню: {str(e)}")
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

class ConfirmButton(nextcord.ui.Button):
    def __init__(self, channel, db):
        self.channel = channel
        self.db = db
        super().__init__(label="Подтвердить", style=nextcord.ButtonStyle.danger)

    async def callback(self, interaction: nextcord.Interaction):
        try:
            await interaction.response.send_message("✅ Комната будет удалена!", ephemeral=True)
            
            await self.db.delete_private_room(self.channel.id)
            
            await self.channel.delete()
            
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Произошла ошибка при удалении: {str(e)}", ephemeral=True)
            except:
                print(f"Ошибка при удалении комнаты: {str(e)}")
            traceback.print_exc()

class PermissionSettingsDropdown(nextcord.ui.Select):
    def __init__(self, channel, owner):
        self.channel = channel
        self.owner = owner
        
        options = [
            nextcord.SelectOption(label="Управление доступом", emoji="🔒", description="Разрешить/запретить подключение"),
            nextcord.SelectOption(label="Кикнуть участника", emoji="🚪", description="Исключить пользователя из комнаты"),
            nextcord.SelectOption(label="Управление микрофоном", emoji="🎙️", description="Мьют/Размьют пользователя"),
            nextcord.SelectOption(label="Видимость канала", emoji="👁️", description="Скрыть/Показать канал"),
            nextcord.SelectOption(label="Доступ для всех", emoji="🔓", description="Открыть/Закрыть комнату для всех")
        ]
        
        super().__init__(
            placeholder="Управление правами", 
            min_values=1, 
            max_values=1, 
            options=options
        )

    async def callback(self, interaction: nextcord.Interaction):
        try:
            if interaction.user != self.owner:
                return await interaction.response.send_message("❌ Только владелец может управлять правами!", ephemeral=True)
                
            if self.values[0] == "Управление доступом":
                view = View(timeout=None)
                view.add_item(UserSelectDropdown(self.channel, "access"))
                await interaction.response.send_message("Выберите пользователя:", view=view, ephemeral=True)
                
            elif self.values[0] == "Кикнуть участника":
                view = View(timeout=None)
                view.add_item(UserSelectDropdown(self.channel, "kick"))
                await interaction.response.send_message("Выберите пользователя для кика:", view=view, ephemeral=True)
                
            elif self.values[0] == "Управление микрофоном":
                view = View(timeout=None)
                view.add_item(UserSelectDropdown(self.channel, "mute"))
                await interaction.response.send_message("Выберите пользователя для управления микрофоном:", view=view, ephemeral=True)
                
            elif self.values[0] == "Видимость канала":
                await self.toggle_visibility(interaction)
                
            elif self.values[0] == "Доступ для всех":
                await self.toggle_access_for_all(interaction)

        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

        try:
            async for message in self.channel.history(limit=100):
                if (message.author == interaction.guild.me and 
                    ((message.embeds and message.embeds[0].title == "Управление приватной комнатой"))):
                    view = View(timeout=None)
                    view.add_item(ChannelSettingsDropdown(self.channel, self.owner))
                    view.add_item(PermissionSettingsDropdown(self.channel, self.owner))
                    
                    embed = message.embeds[0]
                    await message.edit(embed=embed, view=view)
                    break

        except Exception as e:
            print(f"Ошибка при обновлении меню: {str(e)}")

    async def toggle_visibility(self, interaction: nextcord.Interaction):
        try:
            overwrite = self.channel.overwrites
            default_role = interaction.guild.default_role
            current_overwrite = overwrite.get(default_role, nextcord.PermissionOverwrite())
            current_view = current_overwrite.view_channel
            

            if current_view is None:
                new_view = False
            else:
                new_view = not current_view
                
            current_overwrite.update(view_channel=new_view)
            overwrite[default_role] = current_overwrite
            await self.channel.edit(overwrites=overwrite)
            
            message = f"✅ Канал теперь {'виден' if new_view else 'скрыт'} для всех пользователей"
            await interaction.response.send_message(message, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при изменении видимости: {str(e)}", ephemeral=True)
            traceback.print_exc()

    async def toggle_access_for_all(self, interaction: nextcord.Interaction):
        try:
            overwrite = self.channel.overwrites
            default_role = interaction.guild.default_role
            current_overwrite = overwrite.get(default_role, nextcord.PermissionOverwrite())
            current_connect = current_overwrite.connect
            

            if current_connect is None:
                new_connect = True
            else:
                new_connect = not current_connect
                
            current_overwrite.update(connect=new_connect)
            overwrite[default_role] = current_overwrite
            await self.channel.edit(overwrites=overwrite)
            
            message = f"✅ Комната теперь {'открыта' if new_connect else 'закрыта'} для всех пользователей"
            await interaction.response.send_message(message, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при изменении доступа: {str(e)}", ephemeral=True)
            traceback.print_exc()


class UserSelectDropdown(nextcord.ui.UserSelect):
    def __init__(self, channel, action_type):
        self.channel = channel
        self.action_type = action_type
        
        super().__init__(
            placeholder="Выберите пользователя", 
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: nextcord.Interaction):
        try:
            selected_user = self.values[0]
            
            if selected_user not in self.channel.members and self.action_type != "access":
                return await interaction.response.send_message(
                    f"❌ {selected_user.mention} не находится в этой комнате",
                    ephemeral=True
                )
            
            if self.action_type == "access":
                await self.toggle_user_access(interaction, selected_user)
            elif self.action_type == "kick":
                await self.kick_user(interaction, selected_user)
            elif self.action_type == "mute":
                await self.show_mute_options(interaction, selected_user)

        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

    async def toggle_user_access(self, interaction, user):
        try:
            overwrite = self.channel.overwrites
            user_overwrite = overwrite.get(user, nextcord.PermissionOverwrite())
            current_connect = user_overwrite.connect
            
            if current_connect is None:
                new_connect = False
            else:
                new_connect = not current_connect

            if user == interaction.user:
                return await interaction.response.send_message("❌ Вы не можете изменить доступ к комнате для себя", ephemeral=True)
                
            user_overwrite.update(connect=new_connect)
            overwrite[user] = user_overwrite
            await self.channel.edit(overwrites=overwrite)
            
            message = f"✅ {user.mention} теперь {'имеет' if new_connect else 'не имеет'} доступ к комнате"
            await interaction.response.send_message(message, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при изменении доступа: {str(e)}", ephemeral=True)
            traceback.print_exc()

    async def kick_user(self, interaction, user):
        try:
            if user == interaction.user:
                return await interaction.response.send_message("❌ Вы не можете кикнуть себя", ephemeral=True)
                
            await user.move_to(None)
            await interaction.response.send_message(f"✅ {user.mention} был исключен из комнаты", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при исключении пользователя: {str(e)}", ephemeral=True)
            traceback.print_exc()

    async def show_mute_options(self, interaction, user):
        try:
            if user == interaction.user:
                return await interaction.response.send_message("❌ Вы не можете управлять своим микрофоном через бота", ephemeral=True)
                
            view = View(timeout=None)
            view.add_item(MuteButton(self.channel, user, True))
            view.add_item(MuteButton(self.channel, user, False))
            
            await interaction.response.send_message(
                f"Управление микрофоном для {user.mention}:", 
                view=view, 
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

class MuteButton(nextcord.ui.Button):
    def __init__(self, channel, user, is_mute):
        self.channel = channel
        self.user = user
        self.is_mute = is_mute
        
        label = "Замутить" if is_mute else "Размутить"
        style = nextcord.ButtonStyle.danger if is_mute else nextcord.ButtonStyle.success
        
        super().__init__(label=label, style=style)

    async def callback(self, interaction: nextcord.Interaction):
        try:
            await self.user.edit(mute=self.is_mute)
            
            message = f"✅ {self.user.mention} был {'замучен' if self.is_mute else 'размучен'}"
            await interaction.response.send_message(message, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при управлении микрофоном: {str(e)}", ephemeral=True)
            traceback.print_exc()

class DropdownOwn(nextcord.ui.UserSelect):
    def __init__(self, private_voice, user):
        self.private_voice = private_voice
        self.user = user
        self.db = Database()
        
        super().__init__(
            placeholder="Выберите нового владельца",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: nextcord.Interaction):
        try:
            await self.db.connect()
            
            new_owner = self.values[0]
            
            if new_owner == self.user:
                return await interaction.response.send_message("❌ Вы уже являетесь владельцем комнаты", ephemeral=True)
                
            existing_room = await self.db.get_private_room(new_owner.id)
            if existing_room:
                return await interaction.response.send_message(
                    f"❌ {new_owner.mention} уже является владельцем другой приватной комнаты",
                    ephemeral=True
                )
                
            if new_owner not in self.private_voice.members:
                return await interaction.response.send_message(
                    f"❌ {new_owner.mention} должен находиться в комнате, чтобы стать владельцем",
                    ephemeral=True
                )
            
            await self.db.transfer_rights(new_owner.id, self.private_voice.id)
            
            overwrites = self.private_voice.overwrites
            
            old_owner_overwrite = overwrites.get(self.user, nextcord.PermissionOverwrite())
            new_owner_overwrite = overwrites.get(new_owner, nextcord.PermissionOverwrite())
            
            new_owner_overwrite.update(
                manage_channels=True,
                manage_permissions=True,
                connect=True,
                speak=True,
                stream=True,
                priority_speaker=True
            )
            
            old_owner_overwrite.update(
                manage_channels=False,
                manage_permissions=False,
                priority_speaker=False
            )
            
            overwrites[self.user] = old_owner_overwrite
            overwrites[new_owner] = new_owner_overwrite
            
            await self.private_voice.edit(overwrites=overwrites)
            
            await interaction.response.send_message(
                f"✅ {new_owner.mention} назначен новым владельцем комнаты!", 
                ephemeral=True
            )
            
            try:
                await new_owner.send(f"✅ Вы назначены владельцем приватной комнаты **{self.private_voice.name}**!")
            except:
                pass 
            
            try:
                messages_to_delete = []
                async for message in self.private_voice.history(limit=100):
                    if (message.author == self.private_voice.guild.me and 
                        ((message.embeds and message.embeds[0].title == "Управление приватной комнатой"))):
                        messages_to_delete.append(message)
                
                if messages_to_delete:
                    await self.private_voice.delete_messages(messages_to_delete)
                    
            except Exception as e:
                print(f"Ошибка при удалении старых сообщений: {e}")
                for msg in messages_to_delete:
                    try:
                        await msg.delete()
                    except:
                        pass
                    
            try:
                view = View(timeout=None)
                view.add_item(ChannelSettingsDropdown(self.private_voice, new_owner))
                view.add_item(PermissionSettingsDropdown(self.private_voice, new_owner))

                embed = nextcord.Embed(
                    title="Управление приватной комнатой",
                    description=f"👋 Добро пожаловать в управление приватной комнатой!\nТекущий владелец: {new_owner.mention}\nИспользуйте выпадающие меню ниже для управления комнатой.",
                    color=0x2f3136
                )
                
                await self.private_voice.send(embed=embed, view=view)
            except Exception as e:
                print(f"Ошибка при обновлении интерфейса: {e}")
                            
        except nextcord.HTTPException as e:
            await interaction.response.send_message(f"❌ Ошибка Discord: {str(e)}", ephemeral=True)
            traceback.print_exc()
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

class EditLim(nextcord.ui.Modal):
    def __init__(self, private_voice, user):
        super().__init__("Изменение лимита")
        
        self.private_voice = private_voice
        self.user = user
        self.db = Database()
        
        self.edlim = nextcord.ui.TextInput(
            label="Лимит", 
            placeholder="Максимально количество мест: 99", 
            min_length=1, 
            max_length=2, 
            required=True
        )
        self.add_item(self.edlim)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        try:
            await self.db.connect()
            
            try:
                limit = int(self.edlim.value)
                
                if limit < 0 or limit > 99:
                    return await interaction.response.send_message(
                        "❌ Лимит должен быть от 0 до 99", 
                        ephemeral=True
                    )
                    
                await self.private_voice.edit(user_limit=limit)
                
                room_data = await self.db.get_private_room(self.user.id)
                if room_data:
                    await self.db.update_private_room((
                        self.user.id,
                        self.private_voice.name,
                        limit,
                        self.private_voice.id,
                        self.user.id
                    ))
                    
                await interaction.response.send_message(
                    f"✅ Лимит комнаты изменен на: **{limit}**", 
                    ephemeral=True
                )
                
            except ValueError:
                await interaction.response.send_message(
                    "❌ Введите корректное число", 
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

class EditName(nextcord.ui.Modal):
    def __init__(self, private_voice, user):
        super().__init__("Изменение названия")
        
        self.private_voice = private_voice
        self.user = user
        self.db = Database()
        
        self.edname = nextcord.ui.TextInput(
            label="Название", 
            placeholder="Максимально количество символов: 100", 
            min_length=1, 
            max_length=100, 
            required=True
        )
        self.add_item(self.edname)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        try:
            await self.db.connect()
            
            new_name = self.edname.value
            
            await self.private_voice.edit(name=new_name)
            
            room_data = await self.db.get_private_room(self.user.id)
            if room_data:
                await self.db.update_private_room((
                    self.user.id,
                    new_name,
                    self.private_voice.user_limit,
                    self.private_voice.id,
                    self.user.id
                ))
                
            await interaction.response.send_message(
                f"✅ Название комнаты изменено на: **{new_name}**", 
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

class PrivateRoomsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.guild_data = {}
        self.lock = asyncio.Lock() 

    async def init_db(self):
        await self.db.connect()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()
        self.guild_data = {}
        
        try:
            await self.db.connect()
            private_rooms = await self.db.get_all_private_rooms()
            
            for room in private_rooms:
                if room:
                    owner_id, voice_name, voice_limit, voice_id, perms = room
                    channel = self.bot.get_channel(voice_id)
                    
                    if not channel or (isinstance(channel, nextcord.VoiceChannel) and len(channel.members) == 0):
                        await self.db.delete_private_room(voice_id)
                        
                        if channel:
                            try:
                                await channel.delete()
                                print(f"[CLEANUP] Удалена пустая комната: {voice_name} (ID: {voice_id})")
                            except Exception as del_err:
                                print(f"[ERROR] Не удалось удалить канал {voice_name}: {del_err}")
                        else:
                            print(f"[CLEANUP] Удалена запись о несуществующей комнате: {voice_name} (ID: {voice_id})")
        
        except Exception as e:
            print(f"[ERROR] Ошибка при очистке пустых каналов: {str(e)}")
            traceback.print_exc()
            
        for guild_id in GUILD_IDS:
            try:
                data = await self.db.get_guild_channels(guild_id)
                if data:
                    self.guild_data[guild_id] = data
                    print(f"Загружены данные для гильдии {guild_id}: {data}")
                else:
                    print(f"Для гильдии {guild_id} выполните /setup")
            except Exception as e:
                print(f"Ошибка при инициализации данных для гильдии {guild_id}: {str(e)}")
                
        print("Модуль приватных комнат готов!")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        try:
            if member.bot:
                return

            await self.db.connect()
            guild_id = member.guild.id
            
            guild_data = await self.db.get_guild_channels(guild_id)
            
            if not guild_data:
                print(f"Данные не найдены для гильдии {guild_id}. Используйте /setup")
                return
                
            create_channel_id, category_id = guild_data
            
            if after.channel and after.channel.id == create_channel_id: 
                print(f"Пользователь {member.name} подключился к каналу создания")
                await self.create_private_room(member, category_id)

            if before.channel and before.channel.id != create_channel_id: 
                await self.cleanup_old_room(before.channel, create_channel_id)
                
        except Exception as e:
            print(f"Ошибка в обработчике голосового статуса: {str(e)}")
            traceback.print_exc()

    async def create_private_room(self, member: nextcord.Member, category_id: int):
        try:
            await self.db.connect()
            
            existing_room = await self.db.get_private_room(member.id)
            if existing_room:
                voice_id = existing_room[3]
                voice_channel = member.guild.get_channel(voice_id)
                
                if voice_channel and isinstance(voice_channel, nextcord.VoiceChannel):
                    try:
                        await member.move_to(voice_channel)
                        return
                    
                    except Exception as move_error:
                        print(f"[ERROR] Ошибка при перемещении: {str(move_error)}")
                        await self.db.delete_private_room(voice_id)
                else:
                    await self.db.delete_private_room(voice_id)

            guild = member.guild
            category = guild.get_channel(category_id)
            
            if not category or not isinstance(category, nextcord.CategoryChannel):
                raise ValueError("Категория не найдена")

            new_channel = await guild.create_voice_channel(
                name=f"Борщерум {member.display_name}",
                category=category,
                overwrites={
                    guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                    member: nextcord.PermissionOverwrite(
                        connect=True,
                        speak=True,
                        stream=True,
                        priority_speaker=True,
                        manage_channels=True,
                        manage_permissions=True
                    )
                }
            )

            await self.db.update_private_room((
                member.id,              # ownerid
                new_channel.name,       # voicename
                new_channel.user_limit, # voicelim
                new_channel.id,         # voiceid
                member.id               # perms
            ))

            try:
                await member.move_to(new_channel)

            except Exception as move_err:
                print(f"[ERROR] Ошибка при перемещении: {str(move_err)}")

            view = View(timeout=None)
            view.add_item(ChannelSettingsDropdown(new_channel, member))
            view.add_item(PermissionSettingsDropdown(new_channel, member))
            
            try:
                embed = nextcord.Embed(
                    title="Управление приватной комнатой", 
                    description=f"👋 Добро пожаловать в управление вашей приватной комнатой, {member.mention}!\n"
                            f"Используйте выпадающие меню ниже для управления комнатой.",
                    color=0x2f3136
                )
                
                await new_channel.send(embed=embed, view=view)
            except Exception as msg_err:
                print(f"[ERROR] Ошибка отправки сообщения: {str(msg_err)}")

            print(f"[INFO] Создана комната для {member.display_name}")

        except Exception as e:
            print(f"[ERROR] Критическая ошибка в create_private_room: {str(e)}")
            raise

    async def cleanup_old_room(self, channel: nextcord.VoiceChannel, create_chan_id: int):
        try:
            if channel.id == create_chan_id:
                return

            room_data = await self.db.get_private_room_by_channel(channel.id)
            if not room_data:
                return

            if len(channel.members) == 0:
                await self.db.delete_private_room(channel.id)
                await channel.delete()
                print(f"Удалена пустая комната: {channel.name}")
                
        except nextcord.HTTPException as e:
            print(f"Ошибка при удалении комнаты: {str(e)}")
            traceback.print_exc()

        except Exception as e:
            print(f"Непредвиденная ошибка: {str(e)}")
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, deleted_channel):
        try:
            if isinstance(deleted_channel, (nextcord.VoiceChannel, nextcord.CategoryChannel)):
                guild_id = deleted_channel.guild.id
                data = await self.db.get_guild_channels(guild_id)
                
                if data and deleted_channel.id in data:
                    await self.db.delete_guild_channels(guild_id)
                    self.guild_data.pop(guild_id, None)
                    print(f"Автосброс настроек для гильдии {guild_id}")
                    
                room_data = await self.db.get_private_room_by_channel(deleted_channel.id)
                if room_data:
                    await self.db.delete_private_room(deleted_channel.id)
                    print(f"Удален приватный канал из БД: {deleted_channel.name}")

        except Exception as e:
            print(f"Ошибка при обработке удаления канала: {str(e)}")
            traceback.print_exc()

class SetupModal(nextcord.ui.Modal):
    def __init__(self, bot, db, guild_data):
        super().__init__("Настройка приватных комнат")
        self.bot = bot
        self.db = db
        self.guild_data = guild_data
        
        self.category_name = nextcord.ui.TextInput(
            label="Название категории",
            placeholder="Приватные комнаты",
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.category_name)
        
        self.create_channel_name = nextcord.ui.TextInput(
            label="Название канала создания",
            placeholder="➕ Создать комнату",
            min_length=1,
            max_length=100,
            required=True
        )
        self.add_item(self.create_channel_name)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        try:
            guild = interaction.guild
            
            category = await guild.create_category(name=self.category_name.value)
            
            create_channel = await guild.create_voice_channel(
                name=self.create_channel_name.value,
                category=category,
                user_limit=1 
            )
            
            await self.db.save_guild_channels(
                (guild.id, create_channel.id, category.id)
            )
            
            self.guild_data[guild.id] = (create_channel.id, category.id)
            
            await interaction.response.send_message(
                f"✅ Система приватных комнат настроена!\n"
                f"Категория: **{category.name}**\n"
                f"Канал создания: **{create_channel.name}**\n\n"
                f"Чтобы создать приватную комнату, пользователь должен подключиться к каналу **{create_channel.name}**",
                ephemeral=True
            )
        except nextcord.HTTPException as e:
            await interaction.response.send_message(f"❌ Ошибка Discord: {str(e)}", ephemeral=True)
            traceback.print_exc()

        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)
            traceback.print_exc()

def setup(bot):
    bot.add_cog(PrivateRoomsCog(bot))