from config import *
from bot import Bot
from nextcord import Interaction, slash_command, Embed, Color
from nextcord.ext.commands import Cog

class TestSendToChannel(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="test_send_to_channel", description="Отправляет тестовое сообщение в указанный канал", guild_ids=GUILD_IDS)
    async def test_send_to_channel(self, interaction: Interaction, channel_id: str):
        try:
            # Преобразуем ID в число
            channel_id = int(channel_id)
            
            # Получаем канал
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
                return
                
            # Создаем тестовое сообщение
            embed = Embed(
                title="Тестовое сообщение",
                description="Это тестовое сообщение, отправленное через команду /test_send_to_channel",
                color=Color.blue()
            )
            embed.add_field(name="Отправитель", value=interaction.user.mention)
            embed.add_field(name="ID канала", value=str(channel_id))
            
            # Отправляем сообщение
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Сообщение успешно отправлено!", ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("❌ Неверный формат ID канала! ID должен быть числом.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Произошла ошибка: {str(e)}", ephemeral=True)

def setup(bot: Bot):
    bot.add_cog(TestSendToChannel(bot))
