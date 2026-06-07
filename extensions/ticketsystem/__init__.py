from .commands import TicketSystem
from .listener import TicketListeners
from .scores import TicketScores
from .ticket import TicketCategory
from .views import confirm
from .views.containers.MainMenu import MainMenuContainer
from .views.containers.close import CloseContainer
from extensions.ticketsystem.views.containers.ban_appeal.ban_appeal import BanAppealContainer
from extensions.ticketsystem.views.containers.ban_appeal.vpn_ban_appeal import VpnBanAppealContainer
from extensions.ticketsystem.views.containers.rename.rename import RenameContainer


async def setup(bot):
    bot.add_view(view=MainMenuContainer(bot))
    bot.add_view(CloseContainer.for_category(TicketCategory.REPORT))
    bot.add_view(CloseContainer.for_category(TicketCategory.RENAME))
    bot.add_view(CloseContainer.for_category(TicketCategory.BAN_APPEAL))
    bot.add_view(view=confirm.ConfirmView(bot))
    bot.add_view(view=confirm.ConfirmViewStaff(bot))
    bot.add_view(view=RenameContainer())
    bot.add_view(view=BanAppealContainer())
    bot.add_view(view=VpnBanAppealContainer())
    await bot.add_cog(TicketSystem(bot))
    await bot.add_cog(TicketListeners(bot))
    await bot.add_cog(TicketScores(bot))
