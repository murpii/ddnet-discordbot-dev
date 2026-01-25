from .commands import TicketSystem
from .ticket import TicketCategory
from .views import buttons, confirm, subscribe
from .views.buttons import AdminMailButton
from .views.containers import report, rename, complaint, ban_appeal, admin_mail, community_app
from .views.containers.MainMenu import MainMenuContainer
from .views.containers.close import CloseContainer
from .views.containers.ban_appeal import BanAppealContainer
from .views.containers.complaint import ComplaintContainer
from .views.containers.rename import RenameContainer


async def setup(bot):
    bot.add_view(view=MainMenuContainer(bot))
    bot.add_view(CloseContainer.for_category(TicketCategory.REPORT))
    bot.add_view(CloseContainer.for_category(TicketCategory.RENAME))
    bot.add_view(CloseContainer.for_category(TicketCategory.BAN_APPEAL))
    bot.add_view(view=confirm.ConfirmView(bot))
    bot.add_view(view=confirm.ConfirmViewStaff(bot))
    bot.add_view(view=subscribe.SubscribeMenu(bot))
    bot.add_view(view=rename.RenameContainer())
    await bot.add_cog(TicketSystem(bot))
