import discord
from discord import SeparatorSpacing

from constants import Channels
from extensions.ticketsystem.views.buttons import (
    ReportButton,
    BanAppealButton,
    ComplaintButton,
    RenameButton,
    AdminMailButton,
    CommunityAppButton
)


class MainMenuContainer(discord.ui.LayoutView):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# 🎫 Welcome to our Ticket System!"
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "## Report Ticket\n"
                "If you encounter any behavior within the game that violates our rules, such as "
                "**blocking, fun-voting, cheating, or any other form of misconduct**, you can open a "
                "ticket in this given category to address the problem.\n"
                "-# Note: Refrain from creating a ticket for server issues like DoS attacks or in-game lags"
            ),
            discord.ui.ActionRow(ReportButton(self.bot, label="Report Player(s)")),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "## Rename Request\n"
                "Requirements:\n"
                "- The original name should have 3k or more points on it.\n"
                "- Your last rename should be __at least one year ago__.\n"
                "- You must be able to provide proof of owning the points being moved.\n"
                "- The names shouldn't be banned. \n"
                "-# Note:\n"
                "-# If you request a rename and then later change your mind, know that it won't be reverted until at "
                "least one year has passed. Think carefully."
            ),
            discord.ui.ActionRow(RenameButton(self.bot, label="Rename Request")),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "## Ban Appeal\n"
                "If you've been banned unfairly from our in-game servers, you are eligible to appeal the"
                " decision. Please note that ban appeals are not guaranteed to be successful, and our "
                "team reserves the right to deny any appeal at their discretion.\n"
                "-# Note: Only file a ban appeal ticket if you've been banned across all servers."
            ),
            discord.ui.ActionRow(BanAppealButton(self.bot, label="Ban Appeal")),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "## Staff Complaint\n"
                "If a staff member's behavior in our community has caused you concern, you have the "
                "option to make a complaint. Please note that complaints must be "
                "based on specific incidents or behaviors and not on personal biases or general dissatisfaction.\n"
                "-# Note:\n"
                "-# False bans do happen. If you believe you were banned incorrectly, please open a Ban Appeal ticket instead."
            ),
            discord.ui.ActionRow(ComplaintButton(self.bot, label="Staff Complaint")),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "## Admin-Mail (No technical support)\n"
                "If you have an issue or request related to administrative matters, you can use this option. "
                "Explain your issue or request in detail and we will review it and assist you accordingly.\n"
                f"-# Note: For technical issues, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead."
            ),
            discord.ui.ActionRow(
                AdminMailButton(self.bot, label="Admin-Mail"),
                CommunityAppButton(self.bot, label="Community Application")
            ),
            accent_colour=2210995,
        )

        self.add_item(container)
