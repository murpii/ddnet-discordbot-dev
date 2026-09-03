from typing import TYPE_CHECKING

from .manager import PlayerfinderManager
from .overseer import Overseer

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    if bot.pfm is None:
        bot.pfm = PlayerfinderManager(bot)
    await bot.add_cog(Overseer(bot))
