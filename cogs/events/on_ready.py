from nextcord import Activity, ActivityType
from nextcord.ext.commands import Cog
from cogs.events.member_join import VerificationView
from utils.settings_manager import SettingsManager

class OnReady(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(
            activity=Activity(
                type=ActivityType.playing,
                name="/setup для настройки"
            )
        )
        
        # Регистрируем персистентный View для верификации
        await self.register_verification_views()
        
        self.bot.logger.info(f"{self.bot.user} - Успешно запущен и готов к работе!")
    
    async def register_verification_views(self):
        """Регистрирует персистентные View для верификации"""
        try:
            settings_manager = SettingsManager()
            settings = settings_manager.get_all_settings().get("verification", {})
            verification_channel_id = settings.get("verification_channel_id", 0)
            
            if verification_channel_id:
                verification_channel = self.bot.get_channel(verification_channel_id)
                if verification_channel:
                    # Ищем сообщения с компонентами View в канале верификации
                    async for message in verification_channel.history(limit=100):
                        if message.components and message.author == self.bot.user:
                            # Создаем новый View и восстанавливаем его состояние
                            view = VerificationView(self.bot)
                            if await view.restore_state_from_message(message):
                                # Регистрируем восстановленный View
                                self.bot.add_view(view, message_id=message.id)
                                self.bot.logger.info(f"Зарегистрирован персистентный View для сообщения {message.id}")
            
            self.bot.logger.info("Регистрация персистентных View завершена")
            
        except Exception as e:
            self.bot.logger.error(f"Ошибка при регистрации персистентных View: {e}")

def setup(bot):
    bot.add_cog(OnReady(bot))