import asyncio
import nextcord
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any
import os
import yt_dlp
import shutil
import aiohttp
import re
import tempfile
import sys
from pathlib import Path
import time
import uuid
import random
import json
import urllib.parse
from ytmusicapi import YTMusic
import hashlib
from config import AUDIO_FORMAT, AUDIO_QUALITY, FFMPEG_PATH
import logging

logger = logging.getLogger(__name__)

"""
Для работы с YouTube Music API (неофициальный):
- Аутентификация не требуется для базовых операций поиска
- Библиотека ytmusicapi позволяет искать треки и получать информацию о них

Для полноценной работы также требуется установленный FFmpeg:
pip install pynacl

На сервере должен быть установлен FFmpeg:
Windows: https://ffmpeg.org/download.html
Linux: sudo apt-get install ffmpeg
"""

# Основные настройки
TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp"))
PLACEHOLDER_AUDIO = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "no_audio.wav"))
TEMP_MUSIC_DIR = os.path.join(TEMP_DIR, "music")
MUSIC_PATH = os.path.join(TEMP_DIR, "music")

# Проверка пути FFmpeg
print(f"Абсолютный путь к FFmpeg: {FFMPEG_PATH}")
if os.path.exists(FFMPEG_PATH):
    print(f"FFmpeg найден по пути: {FFMPEG_PATH}")
else:
    print(f"FFmpeg не найден по пути: {FFMPEG_PATH}")

# Инициализация YouTube Music API
ytmusic = YTMusic()

# Проверяем и создаем директории
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TEMP_MUSIC_DIR, exist_ok=True)

# Настройки yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(TEMP_DIR, '%(id)s.%(ext)s'),
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'socket_timeout': 15,
    'retries': 3,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': AUDIO_FORMAT,
        'preferredquality': str(AUDIO_QUALITY),
    }],
}

# Проверяем наличие ffmpeg
if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
    ydl_opts['ffmpeg_location'] = FFMPEG_PATH
    print(f"Используем ffmpeg из указанного пути: {FFMPEG_PATH}")
else:
    # Пытаемся использовать ffmpeg из системы
    print(f"Указанный путь к ffmpeg не существует или не указан")
    print("Попробуем использовать ffmpeg из системы")

@dataclass
class Track:
    title: str
    author: str
    url: str
    source: str  # платформа, например 'ytmusic'
    duration: int  # в секундах
    metadata: Any  # дополнительные данные трека
    file_path: Optional[str] = None  # путь к локальному файлу
    is_direct_url: bool = False  # прямая ссылка на аудио (не требует скачивания)
    cached_file: Optional[str] = None  # кэшированный путь к файлу
    id: Optional[str] = None  # ID трека
    video_id: Optional[str] = None  # ID видео (для YouTube Music)
    isrc: Optional[str] = None  # Международный стандартный код записи
    
class MusicBot:
    """Класс для управления музыкальным "под-ботом" для конкретного голосового канала"""
    def __init__(self, voice_client, channel_id):
        self.voice_client = voice_client
        self.channel_id = channel_id
        self.queue: List[Track] = []
        self.played_tracks: List[Track] = []  # Список воспроизведенных треков
        self.current_track: Optional[Track] = None
        self.is_playing = False
        self.is_paused = False
        self.loop = False
        self.loop_current = False
        self.volume = 50  # по умолчанию 50%
        self.task: Optional[asyncio.Task] = None
        self.start_time = 0  # Время начала воспроизведения трека
        self.pause_duration = 0  # Общая продолжительность пауз
        self.pause_start = 0  # Время начала последней паузы
        self.message = None  # Ссылка на сообщение с музыкальным меню
        
        # Создаем временную директорию, если её нет
        os.makedirs(TEMP_DIR, exist_ok=True)
        
    async def download_track(self, track: Optional[Track]) -> str:
        """Скачивает аудио-трек на диск
        
        Возвращает путь к локальному файлу или прямую ссылку на аудио-поток.
        Если загрузка не удалась, возвращает путь к плейсхолдеру.
        """
        if not track:
            print("Пустой трек, возвращаю плейсхолдер")
            return PLACEHOLDER_AUDIO
            
        # Если это прямая ссылка на аудио или локальный файл, возвращаем её
        if track.url and (track.url.startswith("http") and any(ext in track.url for ext in [".mp3", ".wav", ".m4a", ".ogg"])):
            print(f"Прямая ссылка на аудио: {track.url[:50]}...")
            return track.url
            
        # Создаем временную директорию, если не существует
        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)
            print(f"Создана директория для кэширования: {TEMP_DIR}")
            
        # Генерируем имя файла на основе ID трека
        temp_filename = f"{track.id.replace(':', '_')}.mp3"
        temp_file_path = os.path.join(TEMP_DIR, temp_filename)
        
        # Проверяем, существует ли уже скачанный файл
        if os.path.exists(temp_file_path):
            file_size = os.path.getsize(temp_file_path)
            print(f"Найден кэшированный файл: {temp_file_path} (размер: {file_size} байт)")
            if file_size > 1024:  # Убедимся, что файл не пустой
                return temp_file_path
            else:
                print("Файл поврежден или слишком маленький, удаляем")
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    print(f"Ошибка при удалении поврежденного файла: {e}")
                    
        # Формируем поисковый запрос
        search_query = f"{track.author} - {track.title}"
        if track.isrc:
            search_query += f" {track.isrc}"
            
        print(f"Пробую скачать трек: {search_query}")
        
        try:
            # Используем улучшенные настройки для yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_file_path,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtubee': {'player_client': 'WEB'}},
                'geo_bypass': True,
                'socket_timeout': 15,
                'retries': 3,
                'prefer_insecure': True,
                'no_color': True,
                'overwrites': True,
            }
            
            # Проверяем наличие ffmpeg
            if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH
                print(f"Используем ffmpeg из указанного пути: {FFMPEG_PATH}")
            else:
                # Пытаемся использовать ffmpeg из системы
                print(f"Указанный путь к ffmpeg не существует: {FFMPEG_PATH}")
                print("Попробуем использовать ffmpeg из системы")
            
            # Пробуем скачать через YT Music
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Ищем в YouTube Music с ограничением результатов
                    print(f"Поиск и загрузка: ytmsearch1:{search_query}")
                    ydl.download([f"ytmsearch1:{search_query}"])
            except Exception as e:
                print(f"Ошибка при загрузке через YT Music: {str(e)}")
                try:
                    # Если не получилось через YT Music, пробуем через обычный YouTube поиск
                    print(f"Поиск и загрузка через YouTube: ytsearch1:{search_query}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([f"ytsearch1:{search_query}"])
                except Exception as e:
                    # Логируем ошибку и полный стек трассировки для диагностики
                    print(f"Ошибка при загрузке через YouTube: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    print(f"Не удалось загрузить трек: {search_query}. Возвращаем плейсхолдер.")
                    return PLACEHOLDER_AUDIO
            
            # Если не удалось через YT Music, пробуем обычный поиск
            try:
                print(f"Пробую через обычный поиск: ytsearch1:{search_query}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"ytsearch1:{search_query}"])
                    
                    # Снова проверяем успешность загрузки
                    if os.path.exists(temp_file_path):
                        file_size = os.path.getsize(temp_file_path)
                        if file_size > 1024:
                            print(f"Успешно загружен трек через обычный поиск ({file_size} байт)")
                            return temp_file_path
                        else:
                            print("Загруженный файл поврежден или слишком мал")
                    else:
                        print("Файл не создан после загрузки через обычный поиск")
            except Exception as e:
                print(f"Ошибка при загрузке через обычный поиск: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"Общая ошибка при загрузке трека: {e}")
            import traceback
            traceback.print_exc()
            
        print("Все попытки загрузки не удались, возвращаю плейсхолдер")
        return PLACEHOLDER_AUDIO
    
    
    def _get_audio_duration(self, file_path: str) -> Optional[float]:
        """Определяет длительность аудио файла в секундах"""
        try:
            if not os.path.exists(file_path):
                return None
                
            if not os.path.exists(FFMPEG_PATH):
                print(f"FFmpeg не найден, невозможно определить длительность")
                return None
                
            import subprocess
            
            # Получаем информацию о файле с помощью ffprobe
            cmd = [
                FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe"),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate()
            
            if error:
                print(f"Ошибка при определении длительности: {error.decode()}")
                return None
                
            duration = float(output.decode().strip())
            print(f"Длительность аудио файла: {duration} секунд")
            return duration
            
        except Exception as e:
            print(f"Ошибка при получении длительности аудио: {e}")
        return None
    
    async def _get_youtube_info(self, query: str) -> Optional[dict]:
        """Получает информацию о треке с YouTube по поисковому запросу"""
        print("ВНИМАНИЕ: Поиск на YouTube отключен согласно политике приложения")
        return None
    
    async def play_next(self) -> Optional[Track]:
        """Воспроизводит следующий трек из очереди"""
        print("Запуск play_next")

        # Если сейчас включен режим повтора текущего трека, просто воспроизводим тот же трек
        if self.loop_current and self.current_track:
            track_to_play = self.current_track
            print(f"Повторное воспроизведение трека (loop_current): {track_to_play.title}")
        
        # Если очередь пуста, проверяем режим повтора
        elif not self.queue:
            if self.loop and self.played_tracks:
                # В режиме повтора восстанавливаем очередь
                self.queue = self.played_tracks.copy()
                self.played_tracks = []
                return await self.play_next()
            else:
                print("Очередь пуста, воспроизведение остановлено")
                self.is_playing = False
                self.is_paused = False
                self.current_track = None
                return None
        else:
            # Берем следующий трек из очереди
            track_to_play = self.queue.pop(0)
            print(f"Взят следующий трек из очереди: {track_to_play.title}")
            
            # Добавляем трек в список воспроизведенных, если не в режиме loop_current
            if not self.loop_current:
                self.played_tracks.append(track_to_play)
                
        # Устанавливаем текущий трек
        self.current_track = track_to_play
        
        print(f"Подготовка к воспроизведению: {track_to_play.title} (source: {track_to_play.source})")
        
        # Получаем прямую ссылку на аудио в зависимости от источника
        audio_url = None
        
        # Проверяем и устанавливаем путь к ffmpeg
        ffmpeg_executable = FFMPEG_PATH
        if ffmpeg_executable and os.path.exists(ffmpeg_executable):
            print(f"Используем указанный путь к ffmpeg: {ffmpeg_executable}")
        else:
            print("Путь к ffmpeg не указан или не существует. Проверьте наличие ffmpeg.exe в папке ffmpeg проекта.")
            print("Текущий путь: " + str(ffmpeg_executable))
            # Пробуем использовать системный ffmpeg
            ffmpeg_executable = "ffmpeg"
            
        try:
            # Получаем URL для воспроизведения
            if track_to_play.source == 'ytmusic':
                print(f"Получение URL для YouTube Music трека: {track_to_play.title}")
                audio_url = await self._search_ytmusic_track(f"{track_to_play.author} - {track_to_play.title}")
                
                if audio_url:
                    print(f"Получен URL для воспроизведения: {audio_url[:50]}...")
                else:
                    print(f"Не удалось получить URL для трека. Используем плейсхолдер.")
                    # Используем встроенный файл no_audio.wav как плейсхолдер
                    audio_url = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'no_audio.wav')
            else:
                # Для локальных файлов или других источников
                if track_to_play.file_path and os.path.exists(track_to_play.file_path):
                    audio_url = track_to_play.file_path
                elif track_to_play.url:
                    audio_url = track_to_play.url
                else:
                    # Если не удалось найти аудио, используем плейсхолдер
                    audio_url = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'no_audio.wav')
                
            # Проверяем соединение и воспроизводим трек
            if not hasattr(self.voice_client, 'is_connected') or not self.voice_client.is_connected():
                print("Голосовой клиент не подключен. Не могу воспроизвести трек.")
                return None
                
            # Останавливаем предыдущее воспроизведение, если оно активно
            if hasattr(self.voice_client, 'stop') and self.voice_client.is_playing():
                self.voice_client.stop()
                
            # Создаем аудио-источник
            print(f"Создание аудио-источника для трека: {track_to_play.title}")
            
            # Проверяем, это URL или локальный файл
            if audio_url and (audio_url.startswith('http://') or audio_url.startswith('https://')):
                # Опции для потоковых URL
                ffmpeg_options = {
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn'
                }
                
                if ffmpeg_executable:
                    if os.path.exists(ffmpeg_executable):
                        ffmpeg_options['executable'] = ffmpeg_executable
                        print(f"Использую существующий FFmpeg: {ffmpeg_executable}")
                    else:
                        print(f"FFmpeg не найден по пути: {ffmpeg_executable}. Поиск в системном PATH.")
                
                print(f"Создаю аудио-источник для потокового URL с опциями: {ffmpeg_options}")
                try:
                    audio_source = nextcord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
                    print("Аудио-источник успешно создан")
                except Exception as e:
                    print(f"Ошибка при создании аудио-источника: {e}")
                    # Пробуем использовать системный ffmpeg в случае ошибки
                    try:
                        print("Пробую использовать системный FFmpeg")
                        ffmpeg_options.pop('executable', None)
                        audio_source = nextcord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
                        print("Аудио-источник успешно создан с системным FFmpeg")
                    except Exception as e2:
                        print(f"Ошибка при создании аудио-источника с системным FFmpeg: {e2}")
                        raise e
            else:
                # Опции для локальных файлов
                ffmpeg_options = {'options': '-vn'}
                if ffmpeg_executable:
                    if os.path.exists(ffmpeg_executable):
                        ffmpeg_options['executable'] = ffmpeg_executable
                        print(f"Использую существующий FFmpeg: {ffmpeg_executable}")
                    else:
                        print(f"FFmpeg не найден по пути: {ffmpeg_executable}. Поиск в системном PATH.")
                    
                print(f"Создаю аудио-источник для локального файла с опциями: {ffmpeg_options}")
                try:
                    audio_source = nextcord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
                    print("Аудио-источник успешно создан")
                except Exception as e:
                    print(f"Ошибка при создании аудио-источника: {e}")
                    # Пробуем использовать системный ffmpeg в случае ошибки
                    try:
                        print("Пробую использовать системный FFmpeg")
                        ffmpeg_options.pop('executable', None)
                        audio_source = nextcord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
                        print("Аудио-источник успешно создан с системным FFmpeg")
                    except Exception as e2:
                        print(f"Ошибка при создании аудио-источника с системным FFmpeg: {e2}")
                        raise e
                
            # Устанавливаем громкость
            audio_source = nextcord.PCMVolumeTransformer(audio_source)
            audio_source.volume = self.volume / 100.0
            
            # Проверяем подключение еще раз перед воспроизведением
            if not hasattr(self.voice_client, 'is_connected') or not self.voice_client.is_connected():
                print("Голосовой клиент отключился. Не могу воспроизвести трек.")
                return None
                
            # Воспроизводим трек
            print(f"Запускаю воспроизведение трека: {track_to_play.title}")
            self.voice_client.play(audio_source, after=lambda e: self._play_finished(e))
            
            # Устанавливаем флаги состояния
            self.is_playing = True
            self.is_paused = False
            self.start_time = time.time()
            self.pause_duration = 0
            
            return track_to_play
        except Exception as e:
            print(f"Ошибка при воспроизведении трека: {e}")
            import traceback
            traceback.print_exc()
            
            # Пытаемся воспроизвести следующий трек при ошибке
            if self.queue:
                print("Пробуем воспроизвести следующий трек из-за ошибки...")
                return await self.play_next()
                
            return None
    
    async def _update_menu_task(self):
        """Задача для периодического обновления меню, пока играет трек"""
        try:
            # Обновляем меню каждые 11-15 секунд, пока трек воспроизводится
            while self.is_playing and self.current_track and not self.is_paused:
                await asyncio.sleep(random.randint(11, 15))  # Обновляем реже, чтобы не нагружать Discord API
                
                # Проверяем, есть ли у нас сообщение для обновления
                if self.message:
                    try:
                        # Пробуем получить сообщение, чтобы убедиться, что оно существует
                        try:
                            # Проверяем, есть ли у сообщения метод fetch
                            if hasattr(self.message, 'fetch'):
                                # Пробуем получить сообщение, чтобы убедиться, что оно существует
                                try:
                                    await self.message.fetch()
                                except nextcord.errors.NotFound:
                                    print(f"Сообщение не найдено, прекращаю обновление меню для канала {self.channel_id}")
                                    self.message = None
                                    break
                                except Exception as e:
                                    print(f"Не удалось проверить существование сообщения: {e}")
                                    # Продолжаем выполнение, возможно сообщение всё еще существует
                        except Exception as check_error:
                            print(f"Ошибка при проверке сообщения: {check_error}")
                        
                        # Получаем текущую позицию для логирования
                        current_position = self.get_position()
                        current_min, current_sec = divmod(int(current_position), 60)
                        total_min, total_sec = divmod(self.current_track.duration, 60) if self.current_track.duration > 0 else (0, 0)
                        print(f"Обновление прогресса: {current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d} для канала {self.channel_id}")
                        
                        # Создаем новый embed для обновления
                        try:
                            # Создаем новый embed
                            embed = nextcord.Embed(
                                title="🎵 Музыкальное меню",
                                description="Используйте выпадающие списки ниже для управления музыкой.",
                                color=nextcord.Color.blurple()
                            )
                            
                            # Сохраняем поле с ботом, если оно было
                            if hasattr(self.message, 'embeds') and self.message.embeds:
                                for field in self.message.embeds[0].fields:
                                    if field.name == "Музыкальный бот":
                                        embed.add_field(
                                            name=field.name,
                                            value=field.value,
                                            inline=field.inline
                                        )
                                        break
                            
                            # Добавляем информацию о статусе
                            status_emoji = "▶️" if self.is_playing else "⏹️"
                            status_text = "**Воспроизводится**" if self.is_playing else "**Остановлено**"
                            embed.add_field(
                                name="Текущий статус", 
                                value=f"{status_emoji} {status_text}", 
                                inline=False
                            )
                            
                            # Добавляем информацию о текущем треке
                            if self.current_track:
                                source_emoji = "🎧"
                                source_text = "YouTube Music"
                                
                                # Создаем полосу прогресса
                                progress_ratio = current_position / self.current_track.duration if self.current_track.duration > 0 else 0
                                progress_length = 30
                                position = int(progress_ratio * progress_length)
                                bar = "█" * position + "▬" * (progress_length - position)
                                progress_bar = f"`[{bar}]`"
                                
                                time_display = f"`{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}`"
                                
                                track_info = f"**{self.current_track.title}**\nАвтор: {self.current_track.author}\nИсточник: {source_emoji} {source_text}"
                                if self.current_track.duration > 0:
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
                                value="🎧 YouTube Music (поиск по названию или URL)\n📝 Поисковый запрос (поиск через YouTube Music)", 
                                inline=False
                            )
                            
                            # Добавляем информацию о владельце, если она есть
                            owner_name = "Неизвестно"
                            
                            # Пробуем найти информацию о владельце из существующих данных
                            if hasattr(self.message, 'embeds') and self.message.embeds:
                                # Ищем в footer
                                for embed_item in self.message.embeds:
                                    if embed_item.footer and embed_item.footer.text:
                                        # Формат: "Запрошено: username"
                                        if "Запрошено: " in embed_item.footer.text:
                                            owner_name = embed_item.footer.text.replace("Запрошено: ", "")
                                            break
                            
                            embed.set_footer(text=f"Запрошено: {owner_name}")
                            
                            # Пробуем обновить только embed сообщения без изменения view
                            try:
                                await self.message.edit(embed=embed)
                                print(f"Успешно обновлен embed музыкального меню для канала {self.channel_id}")
                            except nextcord.errors.NotFound:
                                print(f"Не удалось обновить сообщение: сообщение не найдено для канала {self.channel_id}")
                                self.message = None
                                break
                            except Exception as embed_error:
                                print(f"Не удалось обновить embed: {embed_error}")
                                
                                # Если не удалось обновить embed, пробуем создать и обновить с новым view
                                try:
                                    # Импортируем MusicMenuView здесь, чтобы избежать циклических импортов
                                    from views.music_menu import MusicMenuView
                                    
                                    # Получаем данные о владельце и канале из существующего сообщения
                                    if hasattr(self.message, 'guild') and self.message.guild:
                                        guild = self.message.guild
                                        
                                        # Находим голосовой канал по ID
                                        voice_channel = None
                                        for vc in guild.voice_channels:
                                            if vc.id == self.channel_id:
                                                voice_channel = vc
                                                break
                                        
                                        # Находим владельца сообщения
                                        owner = None
                                        if hasattr(self.message, 'mentions') and self.message.mentions:
                                            owner = self.message.mentions[0]
                                        elif hasattr(self.message, 'embeds') and self.message.embeds:
                                            # Пробуем получить владельца из footer
                                            embed_data = self.message.embeds[0]
                                            if embed_data.footer and embed_data.footer.text:
                                                # Формат: "Запрошено: username"
                                                username = embed_data.footer.text.replace("Запрошено: ", "")
                                                for member in guild.members:
                                                    if member.display_name == username:
                                                        owner = member
                                                        break
                                        
                                        # Если нашли и владельца, и канал - обновляем меню
                                        if voice_channel:
                                            # Получаем инстанс бота
                                            bot = None
                                            for client in self.message._state._loop._shared_client.values():
                                                if hasattr(client, 'user') and client.user:
                                                    bot = client
                                                    break
                                            
                                            if bot:
                                                try:
                                                    # Создаем новый view
                                                    view = MusicMenuView(bot, owner or None, voice_channel, self)
                                                    view.message = self.message
                                                    
                                                    # Редактируем сообщение
                                                    await self.message.edit(embed=embed, view=view)
                                                    print(f"Успешно обновлено музыкальное меню с новым view для канала {self.channel_id}")
                                                except nextcord.errors.NotFound:
                                                    print(f"Не удалось обновить сообщение с view: сообщение не найдено для канала {self.channel_id}")
                                                    self.message = None
                                                    break
                                                except Exception as edit_error:
                                                    print(f"Ошибка при обновлении сообщения с view: {edit_error}")
                                                    # Если получили ошибку 404, сообщение не существует
                                                    if 'Not Found' in str(edit_error) or '404' in str(edit_error):
                                                        self.message = None
                                                        break
                                        else:
                                            print(f"Не удалось найти канал для {self.channel_id}")
                                    else:
                                        print(f"У сообщения нет guild или guild равен None")
                                except ImportError:
                                    print("Не удалось импортировать MusicMenuView для обновления интерфейса")
                                except Exception as view_error:
                                    print(f"Ошибка при создании нового view: {view_error}")
                                    import traceback
                                    traceback.print_exc()
                        except Exception as menu_content_error:
                            print(f"Ошибка при создании контента меню: {menu_content_error}")
                            import traceback
                            traceback.print_exc()
                    except nextcord.errors.NotFound:
                        print(f"Сообщение не найдено при обновлении меню для канала {self.channel_id}")
                        self.message = None
                        break
                    except Exception as menu_error:
                        print(f"Ошибка при обновлении меню: {menu_error}")
                        import traceback
                        traceback.print_exc()
                        # Если получили ошибку 404, сообщение не существует
                        if 'Not Found' in str(menu_error) or '404' in str(menu_error):
                            self.message = None
                            break
                else:
                    print(f"Нет сообщения для обновления в канале {self.channel_id}")
        except asyncio.CancelledError:
            # Задача была отменена, это нормально
            pass
        except Exception as e:
            print(f"Ошибка в задаче обновления меню: {e}")
            import traceback
            traceback.print_exc()
    
    async def _after_track_finished(self):
        """Вызывается после завершения трека"""
        if self.is_playing and not self.is_paused:
            await self.play_next()
    
    def _play_finished(self, error):
        """Callback-функция, которая вызывается после окончания воспроизведения трека"""
        if error:
            logger.error(f"Ошибка при воспроизведении: {error}")
        
        # Используем существующий event loop
        self.loop.create_task(self._after_track_finished())
    
    async def _cleanup_previous_track(self):
        """Удаляет файл предыдущего трека"""
        if self.current_track and self.current_track.file_path and not self.current_track.is_direct_url:
            try:
                # Проверяем, существует ли файл
                if os.path.exists(self.current_track.file_path):
                    # Если мы не используем режим повтора текущего трека
                    if not self.loop_current:
                        os.remove(self.current_track.file_path)
                        print(f"Удален файл: {self.current_track.file_path}")
            except Exception as e:
                print(f"Ошибка при удалении файла: {e}")
    
    async def _simulate_playback(self, duration: int):
        """Имитация воспроизведения трека для тестирования интерфейса"""
        # В реальном приложении здесь будет воспроизведение через discord voice_client
        # с использованием аудио потока, полученного через другие API
        
        # Для примера используем реальную длительность трека
        await asyncio.sleep(duration)
        
        # Если трек не был остановлен или поставлен на паузу, переходим к следующему
        if self.is_playing and not self.is_paused:
            await self._after_track_finished()
        
    async def disconnect(self):
        """Отключение от голосового канала"""
        if self.voice_client and self.voice_client.is_connected():
            if self.task and not self.task.done():
                self.task.cancel()
            
            # Останавливаем воспроизведение
            if self.voice_client.is_playing():
                self.voice_client.stop()
                
            # Удаляем все скачанные файлы
            await self._cleanup_all_files()
                
            await self.voice_client.disconnect()
            return True
        return False
        
    async def _cleanup_all_files(self):
        """Удаляет все скачанные файлы"""
        try:
            # Удаляем текущий трек
            await self._cleanup_previous_track()
            
            # Удаляем файлы треков в очереди
            for track in self.queue:
                if track.file_path and os.path.exists(track.file_path):
                    os.remove(track.file_path)
                    print(f"Удален файл: {track.file_path}")
        except Exception as e:
            print(f"Ошибка при очистке файлов: {e}")

    async def pause(self):
        """Приостанавливает воспроизведение"""
        if self.is_playing and not self.is_paused and self.voice_client.is_playing():
            self.is_paused = True
            self.voice_client.pause()
            
            # Запоминаем время начала паузы
            self.pause_start = time.time()
            return True
        return False
    
    async def resume(self):
        """Возобновляет воспроизведение"""
        if self.is_paused:
            self.is_paused = False
            self.voice_client.resume()
            
            # Обновляем общую продолжительность пауз
            if self.pause_start > 0:
                self.pause_duration += time.time() - self.pause_start
                self.pause_start = 0
                
            # Запускаем таймер обновления интерфейса
            asyncio.create_task(self._update_menu_task())
                
            return True
        return False
        
    def get_position(self):
        """Получает текущую позицию воспроизведения в секундах"""
        if not self.is_playing or not self.current_track:
            return 0
            
        current_time = time.time()
        
        # Базовая позиция - разница между текущим временем и временем начала воспроизведения
        position = current_time - self.start_time - self.pause_duration
        
        # Если трек на паузе, не учитываем время с момента последней паузы
        if self.is_paused and self.pause_start > 0:
            position -= (current_time - self.pause_start)
            
        # Если это файл-заглушка, симулируем прогресс воспроизведения
        if self.current_track.source == 'ytmusic' or (self.current_track.cached_file and 
                self.current_track.cached_file.endswith('no_audio.wav')):
            # Симулируем прогресс трека, ограничивая максимальное время заглушки 30 секундами
            simulated_duration = min(30, self.current_track.duration if self.current_track.duration > 0 else 30)
            position = position % simulated_duration
            
        # Обеспечиваем, чтобы позиция не превышала длительность трека
        if self.current_track.duration > 0:
            position = min(position, self.current_track.duration)
            
        return max(0, position)  # Не допускаем отрицательных значений

    async def _search_ytmusic_track(self, query: str) -> Optional[str]:
        """Поиск трека на YouTube Music и возвращение прямой ссылки для стриминга"""
        print(f"Начинаю поиск трека на YouTube Music: {query}")
        
        # Проверяем и устанавливаем путь к ffmpeg
        FFMPEG_PATH = os.environ.get('FFMPEG_PATH')
        if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
            print(f"Используем указанный путь к ffmpeg: {FFMPEG_PATH}")
            ffmpeg_location = FFMPEG_PATH
        else:
            print("Путь к ffmpeg не указан или не существует. Используем системный ffmpeg.")
            ffmpeg_location = None
            
        try:
            # Настройки для yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'max_downloads': None,  # Убираем ограничение на количество загрузок
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytmsearch1',  # Сначала ищем через YTMusic
                'extract_flat': False,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            # Добавляем путь к ffmpeg если указан
            if ffmpeg_location:
                ydl_opts['ffmpeg_location'] = ffmpeg_location
                
            print(f"Поиск с опциями yt-dlp: {ydl_opts}")
            
            # Сначала пробуем искать через YouTube Music API
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"Поиск трека через YouTube Music: ytmsearch1:{query}")
                try:
                    info = ydl.extract_info(f"ytmsearch1:{query}", download=False)
                    if not info.get('entries'):
                        print("Не найдено результатов через YTMusic. Переключаюсь на стандартный поиск YouTube.")
                        # Переключаемся на обычный поиск YouTube
                        ydl_opts['default_search'] = 'ytsearch1'
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                            print(f"Поиск трека через обычный YouTube: ytsearch1:{query}")
                            info = ydl2.extract_info(f"ytsearch1:{query}", download=False)
                except Exception as e:
                    print(f"Ошибка при поиске через YTMusic: {e}")
                    # Переключаемся на обычный поиск YouTube
                    ydl_opts['default_search'] = 'ytsearch1'
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                        print(f"Поиск трека через обычный YouTube: ytsearch1:{query}")
                        info = ydl2.extract_info(f"ytsearch1:{query}", download=False)
                        
            # Проверяем, что результаты есть
            if not info or not info.get('entries'):
                print(f"Не найдены результаты для запроса: {query}")
                return None
                
            # Получаем первый результат
            video_info = info['entries'][0]
            print(f"Найден трек: {video_info.get('title')} (ID: {video_info.get('id')})")
            
            # Получаем форматы аудио
            print("Извлечение форматов...")
            with yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'ffmpeg_location': ffmpeg_location}) as ydl:
                detailed_info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_info['id']}", download=False)
            
            # Выбираем формат для аудио
            audio_formats = []
            for format in detailed_info.get('formats', []):
                if format.get('acodec') != 'none' and format.get('vcodec') == 'none':
                    audio_formats.append(format)
            
            if not audio_formats:
                print("Не найдены аудио форматы. Используем 'best' или 'bestaudio'.")
                url = detailed_info.get('url')
                if not url:
                    formats = detailed_info.get('formats', [])
                    # Сортировка по качеству аудио
                    formats.sort(key=lambda x: int(x.get('abr', 0) or 0), reverse=True)
                    if formats:
                        url = formats[0].get('url')
            else:
                # Сортировка по битрейту
                audio_formats.sort(key=lambda x: int(x.get('abr', 0) or 0), reverse=True)
                url = audio_formats[0].get('url')
                
            if url:
                print(f"Получен URL для стриминга: {url[:50]}...")
                return url
            else:
                print("Не удалось получить URL для стриминга")
                return None
                
        except Exception as e:
            print(f"Ошибка при поиске трека: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def add_track(self, voice_channel_id: int, query: str) -> Optional[Track]:
        """Добавляет трек в очередь"""
        print(f"Запрос на добавление трека для канала {voice_channel_id}: {query}")
        
        # Получаем или создаем музыкального бота
        music_bot = await self.get_or_create_music_bot(voice_channel_id)
        if not music_bot:
            print(f"Не удалось получить музыкального бота для канала {voice_channel_id}")
            return None
        
        # Ищем трек
        print(f"Поиск трека для канала {voice_channel_id}: {query}")
        track = await self._search_track(query)
        if not track:
            print(f"Трек не найден: {query}")
            return None
        
        print(f"Найден трек: {track.title} от {track.author} (source: {track.source}, url: {track.url})")
        
        # Добавляем трек в очередь
        music_bot.queue.append(track)
        print(f"Трек добавлен в очередь: {track.title}")
        
        # Если ничего не играет, запускаем воспроизведение
        if not music_bot.is_playing and not music_bot.is_paused:
            print(f"Запускаем воспроизведение для канала {voice_channel_id}")
            await music_bot.play_next()
        else:
            print(f"Трек добавлен в очередь, текущее воспроизведение продолжается")
        
        return track
    
    async def _search_track(self, query: str) -> Optional[Track]:
        """Ищет трек по запросу (URL или текст)"""
        print(f"Начинаю поиск трека: {query}")
        
        # Проверяем, является ли это URL-адресом YouTube или YouTube Music
        if 'youtube.com/watch' in query or 'youtu.be/' in query:
            # Извлекаем video_id из URL
            video_id = None
            if 'youtube.com/watch' in query:
                video_id = query.split('v=')[1].split('&')[0]
            elif 'youtu.be/' in query:
                video_id = query.split('youtu.be/')[1].split('?')[0]
                
            if video_id:
                try:
                    # Получаем информацию о видео с помощью yt-dlp
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query, download=False)
                        
                        title = info.get('title', 'Неизвестный трек')
                        author = info.get('uploader', 'Неизвестный исполнитель')
                        duration = info.get('duration', 0)
                        
                        print(f"Найден трек на YouTube: {title} от {author}")
                            
                        return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                        )
                except Exception as e:
                    print(f"Ошибка при получении информации о YouTube видео: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Проверяем, является ли это URL для YouTube Music
        if 'music.youtube.com' in query:
            try:
                # Извлекаем video_id из URL
                if 'watch?v=' in query:
                    video_id = query.split('watch?v=')[1].split('&')[0]
                    
                    # Получаем информацию о треке с помощью YouTube Music API
                    try:
                        track_info = ytmusic.get_song(video_id)
                        if track_info:
                            title = track_info.get('videoDetails', {}).get('title', 'Неизвестный трек')
                            author = track_info.get('videoDetails', {}).get('author', 'Неизвестный исполнитель')
                            duration = int(track_info.get('videoDetails', {}).get('lengthSeconds', 0))
                            
                            print(f"Найден трек на YouTube Music: {title} от {author}")
                            
                            return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=track_info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                            )
                    except:
                        # Если не удалось через API, пробуем через yt-dlp
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(query, download=False)
                            
                            title = info.get('title', 'Неизвестный трек')
                            author = info.get('uploader', 'Неизвестный исполнитель')
                            duration = info.get('duration', 0)
                            
                            print(f"Найден трек на YouTube Music через yt-dlp: {title} от {author}")
                            
                            return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                            )
                            
            except Exception as e:
                print(f"Ошибка при получении информации о YouTube Music треке: {e}")
                import traceback
                traceback.print_exc()
        
        # Если это не URL, ищем через YouTube Music
        try:
            print(f"Поиск трека через YouTube Music: {query}")
            search_results = ytmusic.search(query, filter='songs', limit=1)
            
            if search_results:
                track_data = search_results[0]
                title = track_data.get('title', 'Неизвестный трек')
                
                # Извлекаем имя первого исполнителя
                author = 'Неизвестный исполнитель'
                if 'artists' in track_data and track_data['artists']:
                    author = track_data['artists'][0].get('name', 'Неизвестный исполнитель')
                
                video_id = track_data.get('videoId')
                duration = 0
                
                # Пытаемся получить продолжительность
                if 'duration' in track_data:
                    duration_str = track_data['duration']
                    # Преобразование из формата MM:SS в секунды
                    if ':' in duration_str:
                        parts = duration_str.split(':')
                        if len(parts) == 2:
                            duration = int(parts[0]) * 60 + int(parts[1])
                
                print(f"Найден трек через YouTube Music: {title} от {author}")
                
                return Track(
                    title=title,
                    author=author,
                    url=f"https://music.youtube.com/watch?v={video_id}" if video_id else "",
                    source='ytmusic',
                    duration=duration,
                    metadata=track_data,
                    id=str(uuid.uuid4()),
                    video_id=video_id,
                    isrc=None
                )
        except Exception as e:
            print(f"Ошибка при поиске в YouTube Music: {e}")
            import traceback
            traceback.print_exc()
        
        # Создаем плейсхолдер для трека, когда поиск не дал результатов
        # Но только если запрос не пустой
        if query.strip():
            dummy_track = Track(
                title=query,
                author="Неизвестный исполнитель",
                url="",
                source="local",
                duration=0,
                metadata=None,
                file_path=None,
                id=str(uuid.uuid4()),
                isrc=None
            )
            
            print(f"Создан плейсхолдер для трека: {query}")
            return dummy_track
        else:
            print("Пустой запрос, трек не создан")
        return None
    
    def get_queue(self, voice_channel_id: int) -> List[Track]:
        """Возвращает текущую очередь треков"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].queue
        return []
    
    def get_current_track(self, voice_channel_id: int) -> Optional[Track]:
        """Возвращает текущий воспроизводимый трек"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].current_track
        return None
    
    def is_playing(self, voice_channel_id: int) -> bool:
        """Проверяет, воспроизводится ли музыка"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].is_playing
        return False
    
    async def skip(self, voice_channel_id: int) -> Optional[Track]:
        """Пропускает текущий трек"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            if music_bot.is_playing or music_bot.is_paused:
                # Останавливаем текущее воспроизведение
                if hasattr(music_bot.voice_client, 'stop'):
                    music_bot.voice_client.stop()
                
                # Воспроизводим следующий трек
                return await music_bot.play_next()
        return None
    
    async def stop(self, voice_channel_id: int) -> bool:
        """Останавливает воспроизведение и очищает очередь"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.queue.clear()
            music_bot.is_playing = False
            music_bot.is_paused = False
            music_bot.current_track = None
            
            if hasattr(music_bot.voice_client, 'stop') and hasattr(music_bot.voice_client, 'is_playing') and music_bot.voice_client.is_playing():
                music_bot.voice_client.stop()
            
            # Очищаем все файлы
            await music_bot._cleanup_all_files()
            
            return True
        return False
    
    async def toggle_loop(self, voice_channel_id: int) -> bool:
        """Включает/выключает режим повтора очереди"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.loop = not music_bot.loop
            # Отключаем повтор текущего трека, если включен повтор очереди
            if music_bot.loop:
                music_bot.loop_current = False
            return music_bot.loop
        return False
    
    async def toggle_loop_current(self, voice_channel_id: int) -> bool:
        """Включает/выключает режим повтора текущего трека"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.loop_current = not music_bot.loop_current
            # Отключаем повтор очереди, если включен повтор текущего трека
            if music_bot.loop_current:
                music_bot.loop = False
            return music_bot.loop_current
        return False
    
    async def set_volume(self, voice_channel_id: int, volume: int) -> bool:
        """Устанавливает громкость (0-100)"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.volume = max(0, min(100, volume))
            
            # Устанавливаем громкость для текущего воспроизведения
            if hasattr(music_bot.voice_client, "source") and music_bot.voice_client.source:
                music_bot.voice_client.source.volume = music_bot.volume / 100.0
            
            return True
        return False
    
    async def pause_music(self, voice_channel_id: int) -> bool:
        """Приостанавливает воспроизведение"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            return await music_bot.pause()
        return False
    
    async def resume_music(self, voice_channel_id: int) -> bool:
        """Возобновляет воспроизведение"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            success = await music_bot.resume()
            
            # Если не на паузе и не воспроизводится, но есть треки в очереди
            if not success and not music_bot.is_playing and music_bot.queue:
                await music_bot.play_next()
                
            return success
        return False
    
    async def disconnect(self, voice_channel_id: int) -> bool:
        """Отключает бота от голосового канала"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            success = await music_bot.disconnect()
            if success:
                del self.music_bots[voice_channel_id]
            return success
        return False
        
    async def cleanup(self):
        """Очищает все подключения и ресурсы"""
        for voice_channel_id, music_bot in list(self.music_bots.items()):
            await music_bot.disconnect()
        self.music_bots.clear()
        self.used_bot_ids.clear()
        
        # Очищаем все временные файлы
        try:
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
                print(f"Временная директория очищена: {TEMP_DIR}")
        except Exception as e:
            print(f"Ошибка при очистке временной директории: {e}")
            
    def set_message(self, voice_channel_id: int, message):
        """Устанавливает ссылку на сообщение с музыкальным меню для конкретного бота"""
        if voice_channel_id in self.music_bots:
            self.music_bots[voice_channel_id].message = message
            print(f"Сохранена ссылка на сообщение для канала {voice_channel_id}")
            return True
        print(f"Не удалось сохранить ссылку на сообщение для канала {voice_channel_id} - бот не найден")
        return False

class MusicManager:
    """Класс для управления несколькими музыкальными ботами в разных голосовых каналах"""
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.queues = {}
        self.current_tracks = {}
        self.message_links = {}
        self.loop = asyncio.get_event_loop()
        
        # Автоматический поиск ffmpeg
        ffmpeg_path = None
        if os.name == 'nt':  # Windows
            # Проверяем стандартные пути установки
            possible_paths = [
                os.path.join(os.environ.get('ProgramFiles', ''), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                'ffmpeg.exe'  # Проверяем PATH
            ]
        else:  # Linux
            possible_paths = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/ffmpeg/bin/ffmpeg',
                'ffmpeg'  # Проверяем PATH
            ]
        
        # Ищем ffmpeg
        for path in possible_paths:
            if os.path.exists(path):
                ffmpeg_path = path
                break
        
        # Настройки для yt-dlp
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'cookiesfrombrowser': ('chrome',),  # Используем cookies из Chrome
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        # Если нашли ffmpeg, добавляем его в настройки
        if ffmpeg_path:
            self.ydl_opts['ffmpeg_location'] = ffmpeg_path
            logger.info(f"Найден ffmpeg по пути: {ffmpeg_path}")
        else:
            logger.warning("ffmpeg не найден, будет использоваться системный ffmpeg из PATH")
        
        self.music_bots = {}  # Словарь, где ключ - ID голосового канала, значение - экземпляр MusicBot
        self.used_bot_ids = set()  # Множество использованных ID ботов
        
    async def get_or_create_music_bot(self, voice_channel_id: int, voice_client=None) -> Optional[MusicBot]:
        """Получает существующего бота или создает нового для указанного голосового канала"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id]
        
        # Если передан голосовой клиент, используем его
        if voice_client:
            music_bot = MusicBot(voice_client, voice_channel_id)
            self.music_bots[voice_channel_id] = music_bot
            return music_bot
            
        # Если не передан голосовой клиент, но есть бот, пытаемся подключиться
        if self.bot:
            try:
                # Находим голосовой канал по ID
                voice_channel = None
                for guild in self.bot.guilds:
                    for vc in guild.voice_channels:
                        if vc.id == voice_channel_id:
                            voice_channel = vc
                            break
                    if voice_channel:
                        break
                
                if voice_channel:
                    # Подключаемся к голосовому каналу
                    print(f"Подключаемся к голосовому каналу {voice_channel.name} ({voice_channel_id})")
                    voice_client = await voice_channel.connect()
                    
                    # Создаем нового музыкального бота
                    music_bot = MusicBot(voice_client, voice_channel_id)
                    self.music_bots[voice_channel_id] = music_bot
                    print(f"Создан новый музыкальный бот для канала {voice_channel_id}")
                    return music_bot
                else:
                    print(f"Не найден голосовой канал с ID {voice_channel_id}")
            except Exception as e:
                print(f"Ошибка при подключении к голосовому каналу: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"Не удалось создать музыкального бота для канала {voice_channel_id}")
        return None
        
    async def add_track(self, voice_channel_id: int, query: str) -> Optional[Track]:
        """Добавляет трек в очередь"""
        print(f"Запрос на добавление трека для канала {voice_channel_id}: {query}")
        
        # Получаем или создаем музыкального бота
        music_bot = await self.get_or_create_music_bot(voice_channel_id)
        if not music_bot:
            print(f"Не удалось получить музыкального бота для канала {voice_channel_id}")
            return None
        
        # Ищем трек
        print(f"Поиск трека для канала {voice_channel_id}: {query}")
        track = await self._search_track(query)
        if not track:
            print(f"Трек не найден: {query}")
            return None
        
        print(f"Найден трек: {track.title} от {track.author} (source: {track.source}, url: {track.url})")
        
        # Добавляем трек в очередь
        music_bot.queue.append(track)
        print(f"Трек добавлен в очередь: {track.title}")
        
        # Если ничего не играет, запускаем воспроизведение
        if not music_bot.is_playing and not music_bot.is_paused:
            print(f"Запускаем воспроизведение для канала {voice_channel_id}")
            await music_bot.play_next()
        else:
            print(f"Трек добавлен в очередь, текущее воспроизведение продолжается")
        
        return track
    
    async def _search_track(self, query: str) -> Optional[Track]:
        """Ищет трек по запросу (URL или текст)"""
        print(f"Начинаю поиск трека: {query}")
        
        # Проверяем, является ли это URL-адресом YouTube или YouTube Music
        if 'youtube.com/watch' in query or 'youtu.be/' in query:
            # Извлекаем video_id из URL
            video_id = None
            if 'youtube.com/watch' in query:
                video_id = query.split('v=')[1].split('&')[0]
            elif 'youtu.be/' in query:
                video_id = query.split('youtu.be/')[1].split('?')[0]
                
            if video_id:
                try:
                    # Получаем информацию о видео с помощью yt-dlp
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query, download=False)
                        
                        title = info.get('title', 'Неизвестный трек')
                        author = info.get('uploader', 'Неизвестный исполнитель')
                        duration = info.get('duration', 0)
                        
                        print(f"Найден трек на YouTube: {title} от {author}")
                            
                        return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                        )
                except Exception as e:
                    print(f"Ошибка при получении информации о YouTube видео: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Проверяем, является ли это URL для YouTube Music
        if 'music.youtube.com' in query:
            try:
                # Извлекаем video_id из URL
                if 'watch?v=' in query:
                    video_id = query.split('watch?v=')[1].split('&')[0]
                    
                    # Получаем информацию о треке с помощью YouTube Music API
                    try:
                        track_info = ytmusic.get_song(video_id)
                        if track_info:
                            title = track_info.get('videoDetails', {}).get('title', 'Неизвестный трек')
                            author = track_info.get('videoDetails', {}).get('author', 'Неизвестный исполнитель')
                            duration = int(track_info.get('videoDetails', {}).get('lengthSeconds', 0))
                            
                            print(f"Найден трек на YouTube Music: {title} от {author}")
                            
                            return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=track_info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                            )
                    except:
                        # Если не удалось через API, пробуем через yt-dlp
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(query, download=False)
                            
                            title = info.get('title', 'Неизвестный трек')
                            author = info.get('uploader', 'Неизвестный исполнитель')
                            duration = info.get('duration', 0)
                            
                            print(f"Найден трек на YouTube Music через yt-dlp: {title} от {author}")
                            
                            return Track(
                                title=title,
                                author=author,
                                url=query,
                                source='ytmusic',
                                duration=duration,
                                metadata=info,
                                id=str(uuid.uuid4()),
                                video_id=video_id,
                                isrc=None
                            )
                            
            except Exception as e:
                print(f"Ошибка при получении информации о YouTube Music треке: {e}")
                import traceback
                traceback.print_exc()
        
        # Если это не URL, ищем через YouTube Music
        try:
            print(f"Поиск трека через YouTube Music: {query}")
            search_results = ytmusic.search(query, filter='songs', limit=1)
            
            if search_results:
                track_data = search_results[0]
                title = track_data.get('title', 'Неизвестный трек')
                
                # Извлекаем имя первого исполнителя
                author = 'Неизвестный исполнитель'
                if 'artists' in track_data and track_data['artists']:
                    author = track_data['artists'][0].get('name', 'Неизвестный исполнитель')
                
                video_id = track_data.get('videoId')
                duration = 0
                
                # Пытаемся получить продолжительность
                if 'duration' in track_data:
                    duration_str = track_data['duration']
                    # Преобразование из формата MM:SS в секунды
                    if ':' in duration_str:
                        parts = duration_str.split(':')
                        if len(parts) == 2:
                            duration = int(parts[0]) * 60 + int(parts[1])
                
                print(f"Найден трек через YouTube Music: {title} от {author}")
                
                return Track(
                    title=title,
                    author=author,
                    url=f"https://music.youtube.com/watch?v={video_id}" if video_id else "",
                    source='ytmusic',
                    duration=duration,
                    metadata=track_data,
                    id=str(uuid.uuid4()),
                    video_id=video_id,
                    isrc=None
                )
        except Exception as e:
            print(f"Ошибка при поиске в YouTube Music: {e}")
            import traceback
            traceback.print_exc()
        
        # Создаем плейсхолдер для трека, когда поиск не дал результатов
        # Но только если запрос не пустой
        if query.strip():
            dummy_track = Track(
                title=query,
                author="Неизвестный исполнитель",
                url="",
                source="local",
                duration=0,
                metadata=None,
                file_path=None,
                id=str(uuid.uuid4()),
                isrc=None
            )
            
            print(f"Создан плейсхолдер для трека: {query}")
            return dummy_track
        else:
            print("Пустой запрос, трек не создан")
        return None
    
    def get_queue(self, voice_channel_id: int) -> List[Track]:
        """Возвращает текущую очередь треков"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].queue
        return []
    
    def get_current_track(self, voice_channel_id: int) -> Optional[Track]:
        """Возвращает текущий воспроизводимый трек"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].current_track
        return None
    
    def is_playing(self, voice_channel_id: int) -> bool:
        """Проверяет, воспроизводится ли музыка"""
        if voice_channel_id in self.music_bots:
            return self.music_bots[voice_channel_id].is_playing
        return False
    
    async def skip(self, voice_channel_id: int) -> Optional[Track]:
        """Пропускает текущий трек"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            if music_bot.is_playing or music_bot.is_paused:
                # Останавливаем текущее воспроизведение
                if hasattr(music_bot.voice_client, 'stop'):
                    music_bot.voice_client.stop()
                
                # Воспроизводим следующий трек
                return await music_bot.play_next()
        return None
    
    async def stop(self, voice_channel_id: int) -> bool:
        """Останавливает воспроизведение и очищает очередь"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.queue.clear()
            music_bot.is_playing = False
            music_bot.is_paused = False
            music_bot.current_track = None
            
            if hasattr(music_bot.voice_client, 'stop') and hasattr(music_bot.voice_client, 'is_playing') and music_bot.voice_client.is_playing():
                music_bot.voice_client.stop()
            
            # Очищаем все файлы
            await music_bot._cleanup_all_files()
            
            return True
        return False
    
    async def toggle_loop(self, voice_channel_id: int) -> bool:
        """Включает/выключает режим повтора очереди"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.loop = not music_bot.loop
            # Отключаем повтор текущего трека, если включен повтор очереди
            if music_bot.loop:
                music_bot.loop_current = False
            return music_bot.loop
        return False
    
    async def toggle_loop_current(self, voice_channel_id: int) -> bool:
        """Включает/выключает режим повтора текущего трека"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.loop_current = not music_bot.loop_current
            # Отключаем повтор очереди, если включен повтор текущего трека
            if music_bot.loop_current:
                music_bot.loop = False
            return music_bot.loop_current
        return False
    
    async def set_volume(self, voice_channel_id: int, volume: int) -> bool:
        """Устанавливает громкость (0-100)"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            music_bot.volume = max(0, min(100, volume))
            
            # Устанавливаем громкость для текущего воспроизведения
            if hasattr(music_bot.voice_client, "source") and music_bot.voice_client.source:
                music_bot.voice_client.source.volume = music_bot.volume / 100.0
            
            return True
        return False
    
    async def pause_music(self, voice_channel_id: int) -> bool:
        """Приостанавливает воспроизведение"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            return await music_bot.pause()
        return False
    
    async def resume_music(self, voice_channel_id: int) -> bool:
        """Возобновляет воспроизведение"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            success = await music_bot.resume()
            
            # Если не на паузе и не воспроизводится, но есть треки в очереди
            if not success and not music_bot.is_playing and music_bot.queue:
                await music_bot.play_next()
                
            return success
        return False
    
    async def disconnect(self, voice_channel_id: int) -> bool:
        """Отключает бота от голосового канала"""
        if voice_channel_id in self.music_bots:
            music_bot = self.music_bots[voice_channel_id]
            success = await music_bot.disconnect()
            if success:
                del self.music_bots[voice_channel_id]
            return success
        return False
        
    async def cleanup(self):
        """Очищает все подключения и ресурсы"""
        for voice_channel_id, music_bot in list(self.music_bots.items()):
            await music_bot.disconnect()
        self.music_bots.clear()
        self.used_bot_ids.clear()
        
        # Очищаем все временные файлы
        try:
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
                print(f"Временная директория очищена: {TEMP_DIR}")
        except Exception as e:
            print(f"Ошибка при очистке временной директории: {e}")
            
    def set_message(self, voice_channel_id: int, message):
        """Устанавливает ссылку на сообщение с музыкальным меню для конкретного бота"""
        if voice_channel_id in self.music_bots:
            self.music_bots[voice_channel_id].message = message
            print(f"Сохранена ссылка на сообщение для канала {voice_channel_id}")
            return True
        print(f"Не удалось сохранить ссылку на сообщение для канала {voice_channel_id} - бот не найден")
        return False