import discord

from constants import Channels
from extensions.ticketsystem.ticket import TicketCategory
from extensions.ticketsystem.views.containers.admin_mail.admin_mail import (
    AdminMailContainer,
)
from extensions.ticketsystem.views.containers.admin_mail.community_app import (
    CommunityAppContainer,
)
from extensions.ticketsystem.views.containers.ban_appeal.ban_appeal import (
    BanAppealContainer,
)
from extensions.ticketsystem.views.containers.ban_appeal.vpn_ban_appeal import (
    VpnBanAppealContainer,
)
from extensions.ticketsystem.views.containers.complaint.complaint import (
    ComplaintContainer,
)
from extensions.ticketsystem.views.containers.rename.rename import RenameContainer
from extensions.ticketsystem.views.containers.report.report import ReportContainer

# category -> the start container shown as the ticket's first message
START_CONTAINERS: dict[TicketCategory, type[discord.ui.LayoutView]] = {
    TicketCategory.REPORT: ReportContainer,
    TicketCategory.RENAME: RenameContainer,
    TicketCategory.BAN_APPEAL: BanAppealContainer,
    TicketCategory.VPN_BAN_APPEAL: VpnBanAppealContainer,
    TicketCategory.COMPLAINT: ComplaintContainer,
    TicketCategory.ADMIN_MAIL: AdminMailContainer,
    TicketCategory.COMMUNITY_APP: CommunityAppContainer,
}

# category -> the LOGS sub-thread a closed ticket's transcript is uploaded to
TRANSCRIPT_THREADS: dict[TicketCategory, Channels] = {
    TicketCategory.REPORT: Channels.TH_REPORTS,
    TicketCategory.BAN_APPEAL: Channels.TH_BAN_APPEALS,
    TicketCategory.VPN_BAN_APPEAL: Channels.TH_BAN_APPEALS,
    TicketCategory.RENAME: Channels.TH_RENAMES,
    TicketCategory.COMPLAINT: Channels.TH_COMPLAINTS,
    TicketCategory.ADMIN_MAIL: Channels.TH_ADMIN_MAIL,
    TicketCategory.COMMUNITY_APP: Channels.TH_COMMUNITY_APPS,
}
