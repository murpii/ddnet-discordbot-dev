import discord

from constants import Channels
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class AdminMailContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Admin Mail](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Please describe your request or issue in as much detail as possible.\n"
                "The more information you provide, the better we can understand and address your "
                "specific concern.\n\n"
                "Feel free to include any relevant background, specific requirements, "
                "or any other details that can help us assist you effectively.",
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                f"-# **Note:** For technical issues, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead."
            ),
            accent_colour=TICKET_ACCENT,
        )

        self.add_item(container)
