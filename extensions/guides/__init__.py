from typing import TYPE_CHECKING

from .commands import HelperCommands
from .context_menu import GuideCtxMenu
from .render import GuideLinkButton

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    await bot.add_cog(HelperCommands(bot))
    await bot.add_cog(GuideCtxMenu(bot))
    bot.add_dynamic_items(GuideLinkButton)
