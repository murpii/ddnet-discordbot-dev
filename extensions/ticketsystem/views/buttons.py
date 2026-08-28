import discord

from extensions.ticketsystem.channel import build_ticket_channel
from extensions.ticketsystem.views.modals import ban_appeal_m, rename_m
from extensions.ticketsystem.ticket import Ticket, TicketCategory

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


class SimpleTicketButton(discord.ui.Button):
    """Main menu button that opens a ticket immediately, without a modal"""

    category: TicketCategory

    def __init__(self, bot: "DDNet", *, label: str, style: discord.ButtonStyle, custom_id: str):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, self.category):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = Ticket(channel=None, creator=interaction.user, category=self.category)
        await build_ticket_channel(interaction, ticket)


class ReportButton(SimpleTicketButton):
    category = TicketCategory.REPORT

    def __init__(self, bot: "DDNet", label: str = TicketCategory.REPORT.value):
        super().__init__(
            bot,
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id="MainMenu:report",
        )


class ComplaintButton(SimpleTicketButton):
    category = TicketCategory.COMPLAINT

    def __init__(self, bot: "DDNet", label: str = TicketCategory.COMPLAINT.value):
        super().__init__(
            bot,
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:complaint",
        )


class AdminMailButton(SimpleTicketButton):
    category = TicketCategory.ADMIN_MAIL

    def __init__(self, bot: "DDNet", label: str = TicketCategory.ADMIN_MAIL.value):
        super().__init__(
            bot,
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:admin-mail",
        )


class CommunityAppButton(SimpleTicketButton):
    category = TicketCategory.COMMUNITY_APP

    def __init__(self, bot: "DDNet", label: str = TicketCategory.COMMUNITY_APP.value):
        super().__init__(
            bot,
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:community-app",
        )


class RenameButton(discord.ui.Button):
    def __init__(self, bot: "DDNet", label: str = TicketCategory.RENAME.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:rename",
        )
        self.bot = bot
        self.ticket = ticket
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.RENAME):
            return

        modal = rename_m.RenameModal(self.bot, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class BanAppealButton(discord.ui.Button):
    def __init__(self, bot: "DDNet", label: str = TicketCategory.RENAME.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:ban-appeal",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.BAN_APPEAL):
            return

        language = str(interaction.locale).split("-")[0]
        modal = ban_appeal_m.BanAppealModal(self.bot, language=language, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class VpnBanAppealButton(discord.ui.Button):
    def __init__(self, bot: "DDNet", label: str = TicketCategory.VPN_BAN_APPEAL.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:vpn-ban-appeal",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.VPN_BAN_APPEAL):
            return

        language = str(interaction.locale).split("-")[0]
        modal = ban_appeal_m.BanAppealModal(
            self.bot,
            language=language,
            ticket=self.ticket,
            category=TicketCategory.VPN_BAN_APPEAL,
        )
        modal.button = self
        await interaction.response.send_modal(modal)
