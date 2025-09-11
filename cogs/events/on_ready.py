from nextcord import Activity, ActivityType
from nextcord.ext.commands import Cog

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
        
        self.bot.logger.info(f"{self.bot.user} - Успешно запущен и готов к работе!")

def setup(bot):
    bot.add_cog(OnReady(bot))