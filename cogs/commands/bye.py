from datetime import datetime, timedelta, timezone
import nextcord
from nextcord import Interaction, slash_command, SlashOption
from nextcord.ext.commands import Cog
from bot import Bot
from config import GUILD_IDS
from utils.settings_manager import settings_manager
from logger import setup_logger

logger = setup_logger()

def _normalize_admin_role_ids(admin_role_ids):
    if isinstance(admin_role_ids, int):
        return [admin_role_ids]
    if isinstance(admin_role_ids, list):
        return admin_role_ids
    return []

class ByeCommand(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="bye", description="Забрать роли, выдать объект инс, удалить сообщения за 24ч", guild_ids=GUILD_IDS)
    async def bye(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(description="Участник")
    ):
        settings = settings_manager.get_all_settings().get("verification", {})
        admin_role_ids = _normalize_admin_role_ids(settings.get("admin_role_ids", []))
        rejected_role_id = settings.get("rejected_role_id", 0)
        if not admin_role_ids:
            await interaction.response.send_message("В настройках верификации не заданы роли администраторов.", ephemeral=True)
            return
        if not any(r.id in admin_role_ids for r in interaction.user.roles):
            await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("Нельзя применить к боту.", ephemeral=True)
            return
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        deleted = 0
        for channel in guild.text_channels:
            try:
                if not channel.permissions_for(guild.me).read_message_history or not channel.permissions_for(guild.me).manage_messages:
                    continue
                before = None
                while True:
                    to_delete = []
                    last_seen = None
                    async for msg in channel.history(limit=100, after=cutoff, before=before):
                        last_seen = msg
                        if msg.author.id == user.id:
                            to_delete.append(msg)
                    if last_seen is None:
                        break
                    if len(to_delete) == 1:
                        try:
                            await to_delete[0].delete()
                            deleted += 1
                        except Exception:
                            pass
                    else:
                        try:
                            await channel.bulk_delete(to_delete)
                            deleted += len(to_delete)
                        except Exception:
                            for m in to_delete:
                                try:
                                    await m.delete()
                                    deleted += 1
                                except Exception:
                                    pass
                    if len(to_delete) < 100:
                        break
                    before = last_seen
            except Exception as e:
                logger.warning(f"Ошибка при удалении сообщений в {channel.id}: {e}")
        roles_to_remove = [r for r in user.roles if r != guild.default_role]
        if roles_to_remove:
            try:
                await user.remove_roles(*roles_to_remove)
            except Exception as e:
                logger.warning(f"Ошибка снятия ролей у {user.id}: {e}")
        if rejected_role_id:
            role = guild.get_role(rejected_role_id)
            if role:
                try:
                    await user.add_roles(role)
                except Exception as e:
                    logger.warning(f"Ошибка выдачи роли объект инс: {e}")
        await interaction.followup.send(f"Готово. Удалено сообщений: {deleted}. Роли сняты, выдана роль объект инс.", ephemeral=True)

def setup(bot: Bot):
    bot.add_cog(ByeCommand(bot))
