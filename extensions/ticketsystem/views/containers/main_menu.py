from typing import TYPE_CHECKING

import discord

from constants import Channels
from extensions.ticketsystem.views.buttons import (
    AdminMailButton,
    BanAppealButton,
    CommunityAppButton,
    ComplaintButton,
    RenameButton,
    ReportButton,
    VpnBanAppealButton,
)
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator

if TYPE_CHECKING:
    from bot import DDNet


class MainMenuContainer(discord.ui.LayoutView):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# 🎫 Welcome to our Ticket System!"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Report Ticket\n"
                "If you encounter any behavior within the game that violates our rules, such as "
                "**blocking, fun-voting, cheating, or any other form of misconduct**, you can open a "
                "ticket in this given category to address the problem.\n\n"
                "-# **Note:** Refrain from creating a ticket for server issues like DoS attacks or in-game lags"
            ),
            discord.ui.ActionRow(ReportButton(self.bot, label="Report Player(s)")),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Rename Request\n"
                "Requirements:\n"
                "- The original name should have 3k or more points on it.\n"
                "- Your last rename should be __at least one year ago__.\n"
                "- You must be able to provide proof of owning the points being moved.\n"
                "- The names shouldn't be banned.\n"
                "**Note:**\n"
                "- Requests may also be declined at our discretion if the player has "
                "an excessive number of bans or bans related to cheating.\n"
                "- If you request a rename and then later change your mind, know that it won't "
                "be reverted until at least one year has passed. Think carefully."
            ),
            discord.ui.ActionRow(RenameButton(self.bot, label="Rename Request")),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Ban Appeal\n"
                "If you've been banned unfairly from our in-game servers, you are eligible to appeal the"
                " decision. Please note that ban appeals are not guaranteed to be successful, and our "
                "team reserves the right to deny any appeal at their discretion.\n\n"
                "-# **Note:** Only file a ban appeal ticket if you've been banned across all servers.\n"
                "-# Use **VPN Ban Appeal** instead if you can't connect because your IP is flagged as a "
                "VPN, proxy or datacenter."
            ),
            discord.ui.ActionRow(
                BanAppealButton(self.bot, label="Ban Appeal"),
                VpnBanAppealButton(self.bot, label="VPN Ban Appeal"),
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Staff Complaint\n"
                "If a staff member's behavior in our community has caused you concern, you have the "
                "option to make a complaint. Please note that complaints must be "
                "based on specific incidents or behaviors and not on personal biases or general dissatisfaction.\n\n"
                "-# **Note:** False bans do happen. If you believe you were banned incorrectly, please open a Ban Appeal ticket instead."
            ),
            discord.ui.ActionRow(ComplaintButton(self.bot, label="Staff Complaint")),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Admin-Mail (No technical support)\n"
                "If you have an issue or request related to administrative matters, you can use this option. "
                "Explain your issue or request in detail and we will review it and assist you accordingly.\n"
                "## Community Application\n"
                "Do you run a server network and want it to be featured in DDNet's server browser?\n"
                "Use \"Community Application\" below to submit your community for review.\n"
                "The ticket will guide you through the requirements and information needed for your application.\n\n"
                f"-# **Note:** For technical issues, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead."
            ),
            discord.ui.ActionRow(
                AdminMailButton(self.bot, label="Admin-Mail"),
                CommunityAppButton(self.bot, label="Community Application")
            ),
            accent_colour=TICKET_ACCENT,
        )

        self.add_item(container)
