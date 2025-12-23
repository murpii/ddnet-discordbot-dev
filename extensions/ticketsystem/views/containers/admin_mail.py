import discord
from discord import SeparatorSpacing

from constants import URLs
from extensions.ticketsystem.manager import Ticket


class AdminMailContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Admin Mail](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "Please describe your request or issue in as much detail as possible.\n"
                "The more information you provide, the better we can understand and address your "
                "specific concern.\n\n"
                "Feel free to include any relevant background, specific requirements, "
                "or any other details that can help us assist you effectively.",
            ),
            accent_colour=2210995,
        )

        self.add_item(container)
