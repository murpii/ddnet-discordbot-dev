from extensions.management.admin.commands import Admin
from extensions.management.admin.hub import AdminHub
from extensions.management.admin.views.hub_view import AdminHubView

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    await bot.add_cog(Admin(bot))
    await bot.add_cog(AdminHub(bot))
    bot.add_view(view=AdminHubView(bot))
