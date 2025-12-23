import discord
from discord import SeparatorSpacing

from extensions.ticketsystem.manager import Ticket


class ReportContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Report Ticket](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "Please follow the steps below so we can handle your report efficiently."
                "```prolog\n1. ESC -> Server Info -> Copy Info (in-game).```"
                "```prolog\n2. Paste the copied text into this chat.```"
                "```prolog\n3. Describe the Problem you are having.```",
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True, ),
            discord.ui.TextDisplay(
                "-# **Important notes**\n"
                "-# Do NOT file reports about server lag or DoS attacks.\n"
                "-# Do NOT report players faking a player other than yourself."
            ),
            accent_colour=2210995,
        )

        self.add_item(container)
