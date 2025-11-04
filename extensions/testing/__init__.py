from .layoutview import Layout


async def setup(bot):
    await bot.add_cog(Layout(bot))
