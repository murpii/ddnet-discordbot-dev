import discord
from discord import SeparatorSpacing

from extensions.ticketsystem.manager import Ticket


class ComplaintContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Staff Complaint](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.TextDisplay(
                "Approach the process with clarity and objectivity. "
                "Here are some steps to help you write an effective complaint: \n\n"
                "Clearly pinpoint the incident or behavior that has caused you concern.\n"
                "Be specific about what happened, when it occurred, and who was involved.\n"
                "Ensure that your complaint is based on objective facts rather than "
                "personal biases or general dissatisfaction.\n"
                "Stick to the specific incident or behavior you are addressing and "
                "avoid making assumptions or generalizations."
            ),
            accent_colour=2210995,
        )

        self.add_item(container)
