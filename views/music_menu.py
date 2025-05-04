import nextcord
from nextcord import Interaction, SelectOption
from utils.music_manager import MusicManager
import asyncio

class TrackSelectMenu(nextcord.ui.Select):
    def __init__(self, music_manager, owner, bot=None, message=None):
        self.music_manager = music_manager
        self.owner = owner
        self.bot = bot
        self.message = message
        
        # Создаем опцию "Добавить трек"
        options = [
            SelectOption(
                label="Добавить трек",
                description="Добавить новый трек в очередь",
                emoji="➕",
                value="add_track",
                default=False  # Явно указываем, что опция не выбрана по умолчанию
            )
        ]
        
        # Получаем текущую очередь и добавляем треки как опции
        # (это будет обновляться при обновлении меню)
        queue = self.music_manager.get_queue(self.owner.voice.channel.id)
        
        # Получаем текущий трек для отображения его по умолчанию
        current_track = self.music_manager.get_current_track(self.owner.voice.channel.id)
        default_option = 0  # По умолчанию "Добавить трек"
        
        # Если есть текущий трек, добавляем его первым после "Добавить трек"
        if current_track:
            # Выбираем эмодзи в зависимости от источника
            emoji = "🎧"
            
            # Обрезаем длинные названия
            title = current_track.title[:40] + ("..." if len(current_track.title) > 40 else "")
            author = current_track.author[:30] + ("..." if len(current_track.author) > 30 else "")
            
            # Добавляем опцию текущего трека
            options.append(
                SelectOption(
                    label=f"▶️ {title}",
                    description=f"Сейчас играет: {author}",
                    value="current_track",
                    emoji=emoji,
                    default=True  # Этот трек будет выбран по умолчанию
                )
            )
            default_option = 1  # Индекс текущего трека
        
        # Добавляем остальные треки из очереди
        for i, track in enumerate(queue[:23]):  # Ограничение в 25 опций (1 добавление + 1 текущий + 23 в очереди)
            # Выбираем эмодзи в зависимости от источника
            emoji = "🎧"
            
            # Обрезаем длинные названия
            title = track.title[:40] + ("..." if len(track.title) > 40 else "")
            author = track.author[:30] + ("..." if len(track.author) > 30 else "")
            
            # Добавляем опцию трека
            options.append(
                SelectOption(
                    label=f"{i+1}. {title}",
                    description=f"Автор: {author}",
                    value=f"track_{i}",
                    emoji=emoji
                )
            )
            
        super().__init__(
            placeholder="Выберите трек или добавьте новый",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.owner.id:
            return await interaction.response.send_message(
                "Только владелец музыкального меню может использовать его!", 
                ephemeral=True
            )
            
        selected_value = self.values[0]
        
        if selected_value == "add_track":
            # Открываем модальное окно для ввода URL трека
            try:
                # Если message не был установлен, используем текущее сообщение
                message = self.message or interaction.message
                # Если bot не был установлен, используем client из interaction
                bot = self.bot or interaction.client
                
                modal = AddTrackModal(
                    self.music_manager, 
                    self.owner.voice.channel.id, 
                    message, 
                    self.owner, 
                    self.owner.voice.channel, 
                    bot
                )
                await interaction.response.send_modal(modal)
            except Exception as e:
                print(f"Ошибка при создании модального окна: {e}")
                await interaction.response.send_message(
                    "Произошла ошибка при создании окна добавления трека. Попробуйте снова.",
                    ephemeral=True
                )
        elif selected_value == "current_track":
            # Выбран текущий трек
            current_track = self.music_manager.get_current_track(self.owner.voice.channel.id)
            if current_track:
                # Получаем длительность в формате минут:секунд
                minutes = current_track.duration // 60
                seconds = current_track.duration % 60
                duration_str = f"{minutes}:{seconds:02d}" if current_track.duration > 0 else "Неизвестно"
                
                # Создаем эмбед с информацией о треке
                embed = nextcord.Embed(
                    title=f"Сейчас играет: {current_track.title}",
                    description=f"Автор: **{current_track.author}**\nДлительность: {duration_str}",
                    color=nextcord.Color.green()
                )
                
                # Добавляем информацию об источнике
                source_emoji = "🎧"
                source_name = "YouTube"
                embed.add_field(name="Источник", value=f"{source_emoji} {source_name}", inline=True)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("Сейчас ничего не воспроизводится", ephemeral=True)
        else:
            # Выбран трек из очереди
            track_index = int(selected_value.split("_")[1])
            # Получаем информацию о треке
            queue = self.music_manager.get_queue(self.owner.voice.channel.id)
            if track_index < len(queue):
                track = queue[track_index]
                await interaction.response.send_message(
                    f"Выбран трек: **{track.title}**\nАвтор: {track.author}", 
                    ephemeral=True
                )
                # Можно добавить дополнительные действия при выборе трека


class ControlSelectMenu(nextcord.ui.Select):
    def __init__(self, music_manager, owner):
        self.music_manager = music_manager
        self.owner = owner
        
        # Проверяем текущее состояние воспроизведения
        voice_channel_id = self.owner.voice.channel.id
        is_playing = self.music_manager.is_playing(voice_channel_id)
        is_paused = False  # По умолчанию не на паузе
        
        # Получаем текущий трек
        current_track = self.music_manager.get_current_track(voice_channel_id)
        if current_track:
            # Ищем бот, который обрабатывает этот канал
            bot_instance = None
            if hasattr(self.music_manager, 'music_bots'):
                for bot_id, bot in self.music_manager.music_bots.items():
                    if bot.channel_id == voice_channel_id:
                        bot_instance = bot
                        break
            
            # Если нашли бот, проверяем состояние паузы
            if bot_instance:
                is_paused = bot_instance.is_paused
        
        options = []
        
        # Добавляем опцию Воспроизвести/Пауза в зависимости от состояния
        if is_playing and not is_paused:
            options.append(
                SelectOption(
                    label="Пауза",
                    description="Приостановить воспроизведение",
                    emoji="⏸️",
                    value="pause"
                )
            )
        else:
            options.append(
            SelectOption(
                label="Воспроизвести",
                description="Начать воспроизведение музыки",
                emoji="▶️",
                value="play"
                )
            )
        
        # Добавляем остальные опции управления
        options.extend([
            SelectOption(
                label="Пропустить",
                description="Пропустить текущий трек",
                emoji="⏭️",
                value="skip"
            ),
            SelectOption(
                label="Остановить",
                description="Остановить воспроизведение и очистить очередь",
                emoji="⏹️",
                value="stop"
            ),
            SelectOption(
                label="Повторять все",
                description="Включить/выключить режим повтора",
                emoji="🔁",
                value="loop"
            ),
            SelectOption(
                label="Повторять текущий",
                description="Включить/выключить повтор текущего трека",
                emoji="🔂",
                value="loop_current"
            ),
            SelectOption(
                label="Громкость",
                description="Изменить уровень громкости",
                emoji="🔊",
                value="volume"
            ),
            SelectOption(
                label="Очередь",
                description="Показать текущую очередь воспроизведения",
                emoji="📃",
                value="queue"
            ),
            SelectOption(
                label="Отключить бота",
                description="Отключить музыкального бота от канала",
                emoji="👋",
                value="disconnect"
            )
        ])
            
        super().__init__(
            placeholder="Управление музыкой",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.owner.id:
            return await interaction.response.send_message(
                "Только владелец музыкального меню может использовать его!", 
                ephemeral=True
            )
            
        voice_channel_id = self.owner.voice.channel.id
        selected_value = self.values[0]
        
        # Флаг успешного выполнения операции
        operation_success = False
        message = ""
        
        if selected_value == "play":
            operation_success = await self.music_manager.resume_music(voice_channel_id)
            message = "▶️ Воспроизведение продолжено"
            
        elif selected_value == "pause":
            operation_success = await self.music_manager.pause_music(voice_channel_id)
            message = "⏸️ Воспроизведение приостановлено"
            
        elif selected_value == "skip":
            skipped_track = await self.music_manager.skip(voice_channel_id)
            operation_success = skipped_track is not None
            message = "⏭️ Трек пропущен"
            
        elif selected_value == "stop":
            operation_success = await self.music_manager.stop(voice_channel_id)
            message = "⏹️ Воспроизведение остановлено"
            
        elif selected_value == "loop":
            is_looping = await self.music_manager.toggle_loop(voice_channel_id)
            operation_success = True
            status = "включен" if is_looping else "выключен"
            message = f"🔁 Режим повтора всех треков {status}"
            
        elif selected_value == "loop_current":
            is_looping = await self.music_manager.toggle_loop_current(voice_channel_id)
            operation_success = True
            status = "включен" if is_looping else "выключен"
            message = f"🔂 Режим повтора текущего трека {status}"
            
        elif selected_value == "volume":
            # Открываем модальное окно для изменения громкости
            modal = VolumeModal(self.music_manager, voice_channel_id)
            await interaction.response.send_modal(modal)
            return
            
        elif selected_value == "queue":
            queue = self.music_manager.get_queue(voice_channel_id)
            if not queue:
                await interaction.response.send_message("Очередь пуста", ephemeral=True)
            else:
                queue_text = "\n".join([f"{i+1}. **{track.title}** - {track.author}" for i, track in enumerate(queue[:10])])
                if len(queue) > 10:
                    queue_text += f"\n... и еще {len(queue) - 10} треков"
                
                embed = nextcord.Embed(
                    title="📃 Очередь воспроизведения",
                    description=queue_text,
                    color=nextcord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Не обновляем меню для просмотра очереди
            return
                
        elif selected_value == "disconnect":
            operation_success = await self.music_manager.disconnect(voice_channel_id)
            message = "👋 Бот отключен от голосового канала"
        
        # Отправляем сообщение о выполнении операции
        await interaction.response.send_message(message, ephemeral=True)
        
        # Обновляем меню после каждого действия
        try:
            # Находим родительское представление
            view = self.view
            if view and hasattr(view, "refresh_menu"):
                # Ждем небольшую задержку для завершения операции
                await asyncio.sleep(0.5)
                
                # Получаем новое взаимодействие для обновления меню
                original_message = interaction.message
                if original_message:
                    # Создаем новое меню
                    new_view = MusicMenuView(
                        self.music_manager.bot,
                        self.owner,
                        self.owner.voice.channel,
                        self.music_manager,
                        original_message
                    )
                    
                    # Обновляем эмбед
                    current_track = self.music_manager.get_current_track(voice_channel_id)
                    is_playing = self.music_manager.is_playing(voice_channel_id)
                    
                    embed = nextcord.Embed(
                        title="🎵 Музыкальное меню",
                        description="Используйте выпадающие списки ниже для управления музыкой.",
                        color=nextcord.Color.blurple()
                    )
                    
                    # Сохраняем информацию о боте из оригинального сообщения
                    if original_message.embeds:
                        original_embed = original_message.embeds[0]
                        for field in original_embed.fields:
                            if field.name == "Музыкальный бот":
                                embed.add_field(
                                    name=field.name,
                                    value=field.value,
                                    inline=field.inline
                                )
                                break
                    
                    # Добавляем информацию о статусе
                    status_emoji = "▶️" if is_playing else "⏹️"
                    status_text = "**Воспроизводится**" if is_playing else "**Остановлено**"
                    
                    embed.add_field(
                        name="Текущий статус", 
                        value=f"{status_emoji} {status_text}", 
                        inline=False
                    )
                    
                    # Добавляем информацию о текущем треке
                    if current_track:
                        # Эмодзи источника
                        source_emoji = "🎧"
                        source_text = "YouTube"
                        
                        # Получаем текущую позицию
                        current_position = 0
                        bot_instance = None
                        if hasattr(self.music_manager, 'music_bots'):
                            for bot_id, bot in self.music_manager.music_bots.items():
                                if bot.channel_id == voice_channel_id:
                                    bot_instance = bot
                                    break
                        
                        if bot_instance and hasattr(bot_instance, 'get_position'):
                            current_position = bot_instance.get_position()
                        
                        # Создаем полосу прогресса
                        progress_bar = new_view.create_progress_bar(current_position, current_track.duration)
                        
                        # Форматируем время
                        current_min, current_sec = divmod(int(current_position), 60)
                        total_min, total_sec = divmod(current_track.duration, 60)
                        time_display = f"`{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}`"
                        
                        # Текст с информацией о треке
                        track_info = f"**{current_track.title}**\nАвтор: {current_track.author}\nИсточник: {source_emoji} {source_text}"
                        
                        # Добавляем полосу прогресса если продолжительность трека известна
                        if current_track.duration > 0:
                            track_info += f"\n\n{progress_bar}\n{time_display}"
                        
                        embed.add_field(
                            name="Текущий трек", 
                            value=track_info, 
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="Текущий трек", 
                            value="Ничего не воспроизводится", 
                            inline=False
                        )
                    
                    # Добавляем подсказку о поддерживаемых источниках
                    embed.add_field(
                        name="Поддерживаемые источники",
                        value="🎧 YouTube (поиск по названию или URL)\n📝 Поисковый запрос (автоматический поиск)",
                        inline=False
                    )
                    
                    embed.set_footer(text=f"Запрошено: {self.owner.display_name}")
                    
                    # Обновляем сообщение с новым эмбедом и представлением
                    await original_message.edit(embed=embed, view=new_view)
            
        except Exception as e:
            print(f"Ошибка при обновлении меню: {e}")


class AddTrackModal(nextcord.ui.Modal):
    def __init__(self, music_manager, voice_channel_id, original_message, owner, voice_channel, bot):
        super().__init__(
            title="Добавить трек",
            timeout=300
        )
        
        self.music_manager = music_manager
        self.voice_channel_id = voice_channel_id
        self.original_message = original_message
        self.owner = owner
        self.voice_channel = voice_channel
        self.bot = bot
        
        self.url = nextcord.ui.TextInput(
            label="URL трека или поисковый запрос",
            placeholder="Введите URL трека на YouTube или поисковый запрос",
            style=nextcord.TextInputStyle.short,
            required=True,
            max_length=200
        )
        
        self.add_item(self.url)
        
    async def callback(self, interaction: Interaction):
        url = self.url.value
        
        # Показываем пользователю, что идёт обработка
        await interaction.response.defer(ephemeral=True)
        
        # Отправляем сообщение о том, что идет поиск трека
        await interaction.followup.send(
            "🔍 Ищу трек и добавляю в очередь...",
            ephemeral=True
        )
        
        # Добавляем трек в очередь
        try:
            track = await self.music_manager.add_track(self.voice_channel_id, url)
            if track:
                # Определяем сообщение в зависимости от источника
                source_emoji = "🎧" 
                source_name = "YouTube"
                
                # Отправляем сообщение об успешном добавлении
                await interaction.followup.send(
                    f"✅ Трек **{track.title}** от **{track.author}** из {source_emoji} {source_name} добавлен в очередь", 
                    ephemeral=True
                )
                
                # Создаем полностью новое меню
                try:
                    # Создаем новое представление
                    new_view = MusicMenuView(self.bot, self.owner, self.voice_channel, self.music_manager, self.original_message)
                    
                    # Создаем эмбед для музыкального меню
                    embed = nextcord.Embed(
                        title="🎵 Музыкальное меню",
                        description="Используйте выпадающие списки ниже для управления музыкой.",
                        color=nextcord.Color.blurple()
                    )
                    
                    # Обновляем эмбед с актуальной информацией
                    current_track = self.music_manager.get_current_track(self.voice_channel.id)
                    is_playing = self.music_manager.is_playing(self.voice_channel.id)
                    
                    # Добавляем информацию о статусе
                    status_emoji = "▶️" if is_playing else "⏹️"
                    status_text = "**Воспроизводится**" if is_playing else "**Остановлено**"
                    
                    embed.add_field(
                        name="Текущий статус", 
                        value=f"{status_emoji} {status_text}", 
                        inline=False
                    )
                    
                    # Добавляем информацию о текущем треке
                    if current_track:
                        # Эмодзи источника
                        source_emoji = "🎧"
                        source_text = "YouTube"
                        
                        # Расчет прогресса
                        current_position = 0
                        bot_instance = None
                        if hasattr(self.music_manager, 'music_bots'):
                            for bot_id, bot in self.music_manager.music_bots.items():
                                if bot.channel_id == self.voice_channel.id:
                                    bot_instance = bot
                                    break
                        
                        if bot_instance and hasattr(bot_instance, 'get_position'):
                            current_position = bot_instance.get_position()
                        
                        # Создаем полосу прогресса
                        progress_bar = new_view.create_progress_bar(current_position, current_track.duration)
                        
                        # Форматируем время
                        current_min, current_sec = divmod(int(current_position), 60)
                        total_min, total_sec = divmod(current_track.duration, 60)
                        time_display = f"`{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}`"
                        
                        # Текст с информацией о треке
                        track_info = f"**{current_track.title}**\nАвтор: {current_track.author}\nИсточник: {source_emoji} {source_text}"
                        
                        # Добавляем полосу прогресса если есть
                        if current_track.duration > 0:
                            track_info += f"\n\n{progress_bar}\n{time_display}"
                        
                        embed.add_field(
                            name="Текущий трек", 
                            value=track_info, 
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="Текущий трек", 
                            value="Ничего не воспроизводится", 
                            inline=False
                        )
                    
                    # Добавляем подсказку о поддерживаемых источниках
                    embed.add_field(
                        name="Поддерживаемые источники",
                        value="🎧 YouTube (поиск по названию или URL)\n📝 Поисковый запрос (поиск через YouTube)", 
                        inline=False
                    )
                    
                    embed.set_footer(text=f"Запрошено: {self.owner.display_name}")
                    
                    # Редактируем оригинальное сообщение с новым представлением
                    await self.original_message.edit(embed=embed, view=new_view)
                    
                    # Отправляем сообщение об успешном обновлении меню
                    await interaction.followup.send(
                        "🔄 Меню обновлено после добавления трека", 
                        ephemeral=True
                    )
                except Exception as e:
                    print(f"Ошибка при создании нового меню: {e}")
                    
                    # Упрощенное обновление меню в случае ошибки
                    try:
                        # Обновляем существующее представление проще
                        if interaction.message and interaction.message.components:
                            view = None
                            # Находим родительское представление
                            for component in interaction.message.components:
                                for child in component.children:
                                    if isinstance(child, nextcord.ui.Select):
                                        view = child.view
                                        break
                                if view:
                                    break
                            
                            if view and hasattr(view, "refresh_menu"):
                                await view.refresh_menu(interaction)
                    except Exception as inner_e:
                        print(f"Ошибка при упрощенном обновлении меню: {inner_e}")
                        
            else:
                await interaction.followup.send(
                    "❌ Не удалось найти трек. Проверьте URL или попробуйте другой запрос.",
                    ephemeral=True
                )
        except Exception as e:
            # Отправляем сообщение об ошибке
            await interaction.followup.send(
                f"❌ Произошла ошибка при добавлении трека: {str(e)}",
                ephemeral=True
            )


class VolumeModal(nextcord.ui.Modal):
    def __init__(self, music_manager, voice_channel_id):
        super().__init__(
            title="Изменить громкость",
            timeout=300
        )
        
        self.music_manager = music_manager
        self.voice_channel_id = voice_channel_id
        
        self.volume = nextcord.ui.TextInput(
            label="Громкость (0-100)",
            placeholder="Введите число от 0 до 100",
            style=nextcord.TextInputStyle.short,
            required=True,
            max_length=3
        )
        
        self.add_item(self.volume)
        
    async def callback(self, interaction: Interaction):
        try:
            volume = int(self.volume.value)
            if 0 <= volume <= 100:
                await self.music_manager.set_volume(self.voice_channel_id, volume)
                await interaction.response.send_message(
                    f"🔊 Громкость установлена на {volume}%", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Значение громкости должно быть от 0 до 100", 
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Введите корректное числовое значение", 
                ephemeral=True
            )


class MusicMenuView(nextcord.ui.View):
    def __init__(self, bot, owner, voice_channel, music_manager=None, message=None):
        super().__init__(timeout=None)  # Бессрочное меню
        
        self.bot = bot
        self.owner = owner
        self.voice_channel = voice_channel
        self.message = message
        
        # Используем переданный music_manager или создаем новый
        self.music_manager = music_manager or MusicManager(bot)
        
        # Добавляем выпадающие меню
        self.add_item(TrackSelectMenu(self.music_manager, owner, self.bot, self.message))
        self.add_item(ControlSelectMenu(self.music_manager, owner))
        
        # Задержка обновления сообщения, чтобы успеть сохранить ссылку
        asyncio.create_task(self._set_message_after_delay())
        
    async def _set_message_after_delay(self):
        """Сохраняет ссылку на сообщение в MusicBot после небольшой задержки"""
        await asyncio.sleep(1)  # Ждем 1 секунду, чтобы сообщение успело установиться
        if self.message and hasattr(self.music_manager, 'set_message'):
            try:
                self.music_manager.set_message(self.voice_channel.id, self.message)
                print(f"Сохранена ссылка на сообщение для канала {self.voice_channel.id}")
            except Exception as e:
                print(f"Ошибка при сохранении ссылки на сообщение: {e}")
        
    async def refresh_menu(self, interaction: Interaction = None):
        """Обновить меню с актуальными данными"""
        # Сохраняем ссылку на сообщение, если ее еще нет
        if not self.message and interaction:
            self.message = interaction.message
            # Сохраняем ссылку на сообщение в MusicBot
            if hasattr(self.music_manager, 'set_message'):
                self.music_manager.set_message(self.voice_channel.id, self.message)
        
        # Если нет ни сообщения, ни интеракции, обновлять нечего
        if not self.message:
            print("Нет сообщения для обновления")
            return
            
        # Удаляем существующие элементы
        self.clear_items()
        
        # Создаем новые экземпляры меню, чтобы гарантировать сброс выбора
        track_select = TrackSelectMenu(self.music_manager, self.owner, self.bot, self.message)
        control_select = ControlSelectMenu(self.music_manager, self.owner)
        
        # Добавляем обновленные меню
        self.add_item(track_select)
        self.add_item(control_select)
        
        # Обновляем эмбед с актуальной информацией
        current_track = self.music_manager.get_current_track(self.voice_channel.id)
        is_playing = self.music_manager.is_playing(self.voice_channel.id)
        
        embed = nextcord.Embed(
            title="🎵 Музыкальное меню",
            description="Используйте выпадающие списки ниже для управления музыкой.",
            color=nextcord.Color.blurple()
        )
        
        # Сохраняем информацию о боте из оригинального сообщения, если она есть
        if self.message.embeds:
            original_embed = self.message.embeds[0]
        for field in original_embed.fields:
            if field.name == "Музыкальный бот":
                embed.add_field(
                    name=field.name,
                    value=field.value,
                    inline=field.inline
                )
                break
        
        status_emoji = "▶️" if is_playing else "⏹️"
        status_text = "**Воспроизводится**" if is_playing else "**Остановлено**"
        
        embed.add_field(
            name="Текущий статус", 
            value=f"{status_emoji} {status_text}", 
            inline=False
        )
        
        if current_track:
            # Добавляем эмодзи в зависимости от источника трека
            source_emoji = "🎧"
            source_text = "YouTube"
            
            # Пытаемся определить текущую позицию воспроизведения
            current_position = 0
            
            # Получаем экземпляр MusicBot, если он существует
            bot_instance = None
            if hasattr(self.music_manager, 'music_bots'):
                for bot_id, bot in self.music_manager.music_bots.items():
                    if bot.channel_id == self.voice_channel.id:
                        bot_instance = bot
                        break
            
            # Получаем текущую позицию воспроизведения
            if bot_instance:
                if hasattr(bot_instance, 'get_position'):
                    current_position = bot_instance.get_position()
            
            # Создаем полосу прогресса
            progress_bar = self.create_progress_bar(current_position, current_track.duration)
            
            # Определяем время в формате минуты:секунды
            current_min, current_sec = divmod(int(current_position), 60)
            total_min, total_sec = divmod(current_track.duration, 60)
            
            time_display = f"`{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}`"
            
            # Добавляем информацию о треке
            track_info = f"**{current_track.title}**\nАвтор: {current_track.author}\nИсточник: {source_emoji} {source_text}"
            
            # Добавляем полосу прогресса если продолжительность трека известна
            if current_track.duration > 0:
                track_info += f"\n\n{progress_bar}\n{time_display}"
                
            embed.add_field(
                name="Текущий трек", 
                value=track_info, 
                inline=False
            )
        else:
            embed.add_field(
                name="Текущий трек", 
                value="Ничего не воспроизводится", 
                inline=False
            )
            
        # Добавляем подсказку о поддерживаемых источниках
        embed.add_field(
            name="Поддерживаемые источники",
            value="🎧 YouTube (поиск по названию или URL)\n📝 Поисковый запрос (автоматический поиск)",
            inline=False
        )
            
        embed.set_footer(text=f"Запрошено: {self.owner.display_name}")
        
        # Обновляем сообщение разными способами в зависимости от наличия interaction
        try:
            if interaction:
                # Если есть interaction, используем его для обновления
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                # Иначе, редактируем сообщение напрямую
                await self.message.edit(embed=embed, view=self)
        except Exception as e:
            print(f"Ошибка при обновлении меню: {e}")
            import traceback
            traceback.print_exc()
        
    def create_progress_bar(self, current, total, length=15):
        """Создает текстовую полосу прогресса"""
        if total <= 0:
            return "`[---------------]`"
            
        # Вычисляем позицию курсора
        ratio = min(1.0, current / total)
        position = int(ratio * length)
        
        # Создаем символы полосы
        bar = "█" * position + "▬" * (length - position)
        
        return f"`[{bar}]`" 