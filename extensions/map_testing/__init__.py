from extensions.map_testing.system import MapTesting
from extensions.map_testing.views.testing_buttons import TestingMenu
from extensions.map_testing.checklist import ChecklistView


async def setup(bot):
    await bot.add_cog(MapTesting(bot))
    bot.add_view(view=TestingMenu(bot))
    bot.add_view(ChecklistView())
