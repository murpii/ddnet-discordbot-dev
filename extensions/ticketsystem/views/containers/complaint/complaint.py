import discord

from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class ComplaintContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Staff Complaint](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "We want to handle your concern fairly and objectively. To help us do that, please describe:\n"
                "- What happened.\n"
                "- When it happened.\n"
                "- Who was involved.\n"
                "Focus on clear, factual details rather than personal opinions or general dissatisfaction.\n"
                "Describe the specific incident or behavior you are reporting and avoid assumptions or broad statements."
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Requirements\n"
                "Upload relevant evidence or supporting information that can strengthen your complaint. "
                "This may include screenshots, message logs or in-game demos."
            ),
            accent_colour=TICKET_ACCENT,
        )

        self.add_item(container)
