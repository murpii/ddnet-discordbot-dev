from .system import TicketSystem
from .views import categories, inner_buttons, confirm, subscribe


async def setup(bot):
    bot.add_view(view=categories.MainMenu(bot))
    bot.add_view(view=inner_buttons.InnerTicketButtons(bot))
    bot.add_view(view=confirm.ConfirmView(bot))
    bot.add_view(view=confirm.ConfirmViewStaff(bot))
    bot.add_view(view=subscribe.SubscribeMenu(bot))
    await bot.add_cog(TicketSystem(bot))