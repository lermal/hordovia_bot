import os
import struct
import wave

def generate_silent_mp3(filename, duration=5, sample_rate=44100):
    """
    Генерирует WAV файл с тишиной указанной длительности
    
    Параметры:
    - filename: путь для сохранения файла
    - duration: длительность в секундах
    - sample_rate: частота дискретизации
    """
    
    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    
    # Открываем файл в режиме записи
    with wave.open(filename, 'w') as wav_file:
        # Устанавливаем параметры
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16 bits
        wav_file.setframerate(sample_rate)
        
        # Вычисляем количество сэмплов
        n_samples = int(duration * sample_rate)
        
        # Генерируем тишину (нулевую амплитуду)
        for _ in range(n_samples):
            wav_file.writeframes(struct.pack('<h', 0))
            
    print(f"Сгенерирован файл тишины: {filename}")
    
if __name__ == "__main__":
    # Генерируем файл тишины в папке assets
    generate_silent_mp3("assets/no_audio.wav", duration=5)
    
    print("Вы можете конвертировать WAV в MP3 с помощью ffmpeg:")
    print("ffmpeg -i assets/no_audio.wav assets/no_audio.mp3") 