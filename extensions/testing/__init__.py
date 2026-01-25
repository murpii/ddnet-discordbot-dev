from .layoutview import Layout
from .queries import StatsCog


async def setup(bot):
    await bot.add_cog(Layout(bot))
    await bot.add_cog(StatsCog(bot))
