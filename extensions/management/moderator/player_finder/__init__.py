from .manager import PlayerfinderManager
from .overseer import Overseer


async def setup(bot):
    if bot.pfm is None:
        bot.pfm = PlayerfinderManager(bot)
    await bot.add_cog(Overseer(bot))
