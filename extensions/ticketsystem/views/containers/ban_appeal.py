import discord
from discord import SeparatorSpacing

from extensions.ticketsystem.manager import Ticket


class BanAppealContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Ban Appeal Ticket](https://-/) \n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!",
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),  # noqa
            discord.ui.TextDisplay(
                "When writing your appeal, please aim to be clear and straightforward in your explanation. "
                "Be honest about what occurred and take ownership for any actions that may have "
                "resulted in your ban.\n\n"
                "Additionally, if you have any evidence, such as screenshots or chat logs that may support your "
                "case, please include it in your appeal.",
            ),
            accent_colour=2210995,
        )
        self.add_item(container)
