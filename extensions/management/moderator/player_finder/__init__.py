from .overseer import Overseer


async def setup(bot):
    await bot.add_cog(Overseer(bot))
