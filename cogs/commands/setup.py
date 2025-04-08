from nextcord import (
    Interaction,
    Permissions,
    slash_command,
    CategoryChannel,
    VoiceChannel,
    Forbidden,
    HTTPException
)
from bot import Bot
from nextcord.ext.commands import Cog
from config import GUILD_IDS 

class SetupCommand(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(
        description="Setup the bot", 
        guild_ids=GUILD_IDS,
        default_member_permissions=Permissions(administrator=True)
    )
    async def setup(self, interaction: Interaction):
        try:
            guild = interaction.guild
            if not guild:
                return await interaction.response.send_message(
                    "Команда доступна только на сервере.",
                    ephemeral=True
                )

            # Проверка через кеш
            if guild.id in self.bot.channel_cache:
                return await interaction.response.send_message(
                    "Сначала удалите существующие каналы.",
                    ephemeral=True
                )

            # Проверка прав бота
            if not guild.me.guild_permissions.manage_channels:
                return await interaction.response.send_message(
                    "Недостаточно прав.",
                    ephemeral=True
                )

            # Создание каналов
            category: CategoryChannel = await guild.create_category(
                name="Bot System",
                reason=f"Setup by {interaction.user}"
            )
            
            channel: VoiceChannel = await guild.create_voice_channel(
                name="bot-channel",
                category=category,
                reason=f"Setup by {interaction.user}"
            )

            # Обновление кеша и БД
            self.bot.channel_cache[guild.id] = (channel.id, category.id)
            await self.bot.db.set_channel(guild.id, channel.id, category.id)

            await interaction.response.send_message(
                f"Система настроена! Канал: {channel.mention}",
                ephemeral=True
            )

        except Forbidden:
            await interaction.response.send_message(
                "Недостаточно прав!",
                ephemeral=True
            )
        except HTTPException as e:
            await interaction.response.send_message(
                f"Ошибка Discord API: {e.text}",
                ephemeral=True
            )

    @Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if channel.guild.id in self.bot.channel_cache:
            if channel.id == self.bot.channel_cache[channel.guild.id][0]:
                del self.bot.channel_cache[channel.guild.id]
                await self.bot.db.conn.execute(
                    "DELETE FROM channels WHERE guild_id = ?",
                    (channel.guild.id,)
                )
                await self.bot.db.conn.commit()

def setup(bot: Bot):
    bot.add_cog(SetupCommand(bot))