# from nextcord.ext import commands
# from nextcord.ui import Select, View, Button, Modal, TextInput
# import aiosqlite
# import nextcord
# from config import *
# from typing import Optional, Tuple

# class Voice(commands.Cog):
#     def __init__(self, bot: commands.Bot):
#         self.bot = bot

#     @commands.Cog.listener("on_ready")
#     async def on_ready(self):
#         cursor.execute("""CREATE TABLE IF NOT EXISTS privates(
#             ownerid BIGINT,
#             voicename TEXT,
#             voicelim INT,
#             overwrites TEXT,
#             voiceid BIGINT,
#             perms BIGINT);
#         """)
#         connection.commit()

#         guild = self.bot.get_guild(guild_id)
#         if guild:
#             category = nextcord.utils.get(guild.categories, id=category_id)
#             if category and isinstance(category, nextcord.CategoryChannel):
#                 for channel in guild.voice_channels:
#                     if channel.id != create_private_chan_id:
#                         await channel.delete()
#                         print('Обнаружил лишний голосовой канал {} ({})'.format(channel.name, channel.id))
#         else:
#             print("Guild not found.")
    
#         strt_send = guild.get_channel(private_control_id)

# class PrivateRooms(commands.Cog):
#     def __init__(self, bot: commands.Bot):
#         self.bot = bot
#         self.db = Database()


# async def setup(bot):
#     await bot.add_cog(PrivateRooms(bot))