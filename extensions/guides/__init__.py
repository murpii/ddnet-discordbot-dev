from .commands import HelperCommands
from .context_menu import GuideCtxMenu
from .render import GuideLinkButton


async def setup(bot):
    await bot.add_cog(HelperCommands(bot))
    await bot.add_cog(GuideCtxMenu(bot))
    bot.add_dynamic_items(GuideLinkButton)
