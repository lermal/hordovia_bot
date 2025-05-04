import os
import sys
import urllib.request
import zipfile
import shutil
import platform
from pathlib import Path

FFMPEG_WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_LINUX_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"

def get_platform():
    """Определяет текущую операционную систему"""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    elif system == "Linux":
        return "Linux"
    elif system == "Darwin":
        return "MacOS"
    else:
        return "Unknown"

def download_file(url, target_path):
    """Скачивает файл из URL"""
    print(f"Скачивание ffmpeg из {url}...")
    try:
        urllib.request.urlretrieve(url, target_path)
        print(f"Скачано в {target_path}")
        return True
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        return False

def extract_zip_windows(zip_path, extract_to):
    """Распаковывает zip-архив для Windows"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            print(f"Распаковка архива...")
            zip_ref.extractall(extract_to)
        
        # Находим папку с ffmpeg в распакованном архиве
        for root, dirs, files in os.walk(extract_to):
            for file in files:
                if file.lower() == "ffmpeg.exe":
                    ffmpeg_path = os.path.join(root, file)
                    target_path = os.path.join("ffmpeg", "ffmpeg.exe")
                    
                    # Копируем файл в целевую директорию
                    os.makedirs("ffmpeg", exist_ok=True)
                    shutil.copy2(ffmpeg_path, target_path)
                    print(f"FFmpeg установлен: {os.path.abspath(target_path)}")
                    
                    # Удаляем временные файлы
                    shutil.rmtree(extract_to)
                    os.remove(zip_path)
                    return True
                    
        print("FFmpeg не найден в распакованном архиве")
        return False
    
    except Exception as e:
        print(f"Ошибка при распаковке: {e}")
        return False

def install_ffmpeg_windows():
    """Устанавливает ffmpeg для Windows"""
    temp_dir = "ffmpeg_temp"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = os.path.join(temp_dir, "ffmpeg.zip")
    
    # Скачиваем архив
    if not download_file(FFMPEG_WINDOWS_URL, zip_path):
        return False
    
    # Распаковываем архив
    return extract_zip_windows(zip_path, temp_dir)

def main():
    print("Установка FFmpeg для работы музыкального бота")
    
    platform_name = get_platform()
    print(f"Операционная система: {platform_name}")
    
    if platform_name == "Windows":
        success = install_ffmpeg_windows()
    else:
        print(f"Для {platform_name} автоматическая установка не поддерживается.")
        print("Пожалуйста, установите ffmpeg вручную и добавьте его в PATH.")
        print("Инструкции: https://ffmpeg.org/download.html")
        success = False
    
    if success:
        print("FFmpeg успешно установлен!")
        print("Теперь вы можете запустить бота.")
    else:
        print("Не удалось установить FFmpeg.")
        print("Пожалуйста, установите его вручную с сайта https://ffmpeg.org/download.html")

if __name__ == "__main__":
    main() 