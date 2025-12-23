from .system import TicketSystem
from .views import buttons, inner_buttons, confirm, subscribe
from .views.containers import report, rename, complaint, ban_appeal, admin_mail, community_app
from .views.containers.MainMenu import MainMenuContainer


async def setup(bot):
    bot.add_view(view=MainMenuContainer(bot))
    bot.add_view(view=inner_buttons.BaseTicketButtons(bot))
    bot.add_view(view=inner_buttons.ReportTicketButtons(bot))
    bot.add_view(view=inner_buttons.BanAppealTicketButtons(bot))
    bot.add_view(view=inner_buttons.RenameTicketButtons(bot))
    bot.add_view(view=confirm.ConfirmView(bot))
    bot.add_view(view=confirm.ConfirmViewStaff(bot))
    bot.add_view(view=subscribe.SubscribeMenu(bot))
    bot.add_view(view=rename.RenameContainer())
    # bot.add_view(view=report.ReportContainer())
    await bot.add_cog(TicketSystem(bot))
