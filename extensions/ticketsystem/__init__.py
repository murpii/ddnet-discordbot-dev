from typing import TYPE_CHECKING

from extensions.ticketsystem.views.containers.admin_mail.community_app import (
    CommunityAppContainer,
)
from extensions.ticketsystem.views.containers.ban_appeal.ban_appeal import (
    BanAppealContainer,
)
from extensions.ticketsystem.views.containers.ban_appeal.vpn_ban_appeal import (
    VpnBanAppealContainer,
)
from extensions.ticketsystem.views.containers.rename.rename import RenameContainer

from .commands import TicketSystem
from .listener import TicketListeners
from .manager import TicketManager
from .scores import TicketScores
from .ticket import TicketCategory
from .views import confirm
from .views.containers.close import CloseContainer
from .views.containers.main_menu import MainMenuContainer

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    if bot.ticket_manager is None:
        bot.ticket_manager = TicketManager(bot)
    bot.add_view(view=MainMenuContainer(bot))
    bot.add_view(CloseContainer.for_category(TicketCategory.REPORT))
    bot.add_view(CloseContainer.for_category(TicketCategory.RENAME))
    bot.add_view(CloseContainer.for_category(TicketCategory.BAN_APPEAL))
    bot.add_view(view=confirm.ConfirmView(bot))
    bot.add_view(view=confirm.ConfirmViewStaff(bot))
    bot.add_view(view=RenameContainer())
    bot.add_view(view=BanAppealContainer())
    bot.add_view(view=VpnBanAppealContainer())
    bot.add_view(view=CommunityAppContainer())
    await bot.add_cog(TicketSystem(bot))
    await bot.add_cog(TicketListeners(bot))
    await bot.add_cog(TicketScores(bot))
