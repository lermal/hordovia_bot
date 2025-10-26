import json
import os
from typing import Dict, Any, Callable, List
import logging

class SettingsManager:
    def __init__(self):
        self.settings_file = "data/settings.json"
        self.settings: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}  # Callbacks для уведомления об изменениях
        self._load_settings()

    def _load_settings(self):
        """Загружает настройки из файла"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except Exception as e:
                print(f"Ошибка при загрузке настроек: {e}")
                self.settings = self._get_default_settings()
        else:
            self.settings = self._get_default_settings()
            self._save_settings()

    def _save_settings(self):
        """Сохраняет настройки в файл"""
        os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)

    def _get_default_settings(self) -> Dict[str, Any]:
        """Возвращает настройки по умолчанию"""
        return {
            "music": {
                "audio_format": "mp3",
                "audio_quality": 192,
                "ffmpeg_path": ""
            },
            "twitch": {
                "notification_channel": 0,
                "check_interval": 15
            },
            "general": {
                "log_level": "INFO",
                "load_exceptions": []
            },
            "private_rooms": {
                "default_category_name": "Приватные комнаты",
                "default_create_channel_name": "➕ Создать комнату",
                "default_user_limit": 0,
                "room_name_template": "{user} - комната"
            },
            "verification": {
                "welcome_channel_id": 0,
                "verification_channel_id": 0,
                "member_role_id": 0,
                "rejected_role_id": 0,
                "admin_role_ids": []
            }
        }

    def get_setting(self, category: str, key: str) -> Any:
        """Получает значение настройки"""
        return self.settings.get(category, {}).get(key)

    def set_setting(self, category: str, key: str, value: Any):
        """Устанавливает значение настройки"""
        if category not in self.settings:
            self.settings[category] = {}
        self.settings[category][key] = value
        self._save_settings()
        self._notify_callbacks(category)

    def get_all_settings(self) -> Dict[str, Any]:
        """Возвращает все настройки"""
        return self.settings

    def update_settings(self, category: str, settings: Dict[str, Any]):
        """Обновляет все настройки категории"""
        self.settings[category] = settings
        self._save_settings()
        self._notify_callbacks(category)
    
    def subscribe_to_category(self, category: str, callback: Callable[[Dict[str, Any]], None]):
        """Подписывается на изменения настроек в категории"""
        if category not in self._callbacks:
            self._callbacks[category] = []
        self._callbacks[category].append(callback)
    
    def unsubscribe_from_category(self, category: str, callback: Callable[[Dict[str, Any]], None]):
        """Отписывается от изменений настроек в категории"""
        if category in self._callbacks and callback in self._callbacks[category]:
            self._callbacks[category].remove(callback)
    
    def _notify_callbacks(self, category: str):
        """Уведомляет всех подписчиков об изменении настроек в категории"""
        if category in self._callbacks:
            category_settings = self.settings.get(category, {})
            for callback in self._callbacks[category]:
                try:
                    callback(category_settings)
                except Exception as e:
                    logging.error(f"Ошибка в callback для категории {category}: {e}") 