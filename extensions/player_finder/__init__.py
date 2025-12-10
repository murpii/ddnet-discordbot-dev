from extensions.player_finder.overseer import Overseer, PlayerFinder


async def setup(bot):
    await bot.add_cog(Overseer(bot))
    # await bot.add_cog(PlayerFinder(bot))
