from extensions.chat.commands.app_commands import Botscribe
from extensions.chat.commands.context_menu import ChatCtxMenu


async def setup(bot):
    await bot.add_cog(ChatCtxMenu(bot))
    await bot.add_cog(Botscribe(bot))
