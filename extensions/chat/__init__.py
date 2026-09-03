from typing import TYPE_CHECKING

from extensions.chat.commands.app_commands import Botscribe
from extensions.chat.commands.context_menu import ChatCtxMenu

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    await bot.add_cog(ChatCtxMenu(bot))
    await bot.add_cog(Botscribe(bot))
