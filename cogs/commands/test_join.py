from config import *
from bot import Bot
from nextcord import Interaction, slash_command, Member
from nextcord.ext.commands import Cog
from ..events.member_join import MemberJoinEvent

class TestJoinCommand(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.member_join_cog = None

    @slash_command(
        name="test_join",
        description="Тестирование функционала присоединения пользователя",
        force_global=True
    )
    async def test_join(self, interaction: Interaction, member: Member = None):
        # Если пользователь не указан, используем автора команды
        target_member = member or interaction.user
        
        # Получаем экземпляр MemberJoinEvent
        if not self.member_join_cog:
            self.member_join_cog = self.bot.get_cog("MemberJoinEvent")
        
        if not self.member_join_cog:
            await interaction.response.send_message("Ошибка: не удалось найти обработчик присоединения", ephemeral=True)
            return
            
        # Отправляем эфемерное сообщение о начале тестирования
        await interaction.response.send_message(
            f"Тестирование присоединения пользователя {target_member.mention}...",
            ephemeral=True
        )
        
        # Вызываем обработчик присоединения
        await self.member_join_cog.on_member_join(target_member)
        
        # Отправляем сообщение об успешном выполнении
        try:
            await interaction.followup.send(
                f"Тестовое присоединение для {target_member.mention} выполнено успешно!",
                ephemeral=True
            )
        except:
            pass

def setup(bot: Bot):
    bot.add_cog(TestJoinCommand(bot)) 