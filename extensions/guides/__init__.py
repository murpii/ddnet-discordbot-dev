from .commands import HelperCommands
from .render import GuideLinkButton


async def setup(bot):
    cog = HelperCommands(bot)
    await bot.add_cog(cog)
    cog.register_all_guides()
    bot.add_dynamic_items(GuideLinkButton)
