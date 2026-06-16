import discord

from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.text import slugify2


class BanAppealContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket | None = None):
        super().__init__(timeout=None)

        greeting = (
            f"Hello {ticket.creator.mention}, thanks for reaching out!"
            if ticket is not None else "Thanks for reaching out!"
        )

        items = [
            discord.ui.TextDisplay(
                "# [Ban Appeal Ticket](https://-/)\n"
                f"{greeting}"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "When writing your appeal, please aim to be clear and straightforward in your explanation. "
                "Be honest about what occurred and take ownership for any actions that may have "
                "resulted in your ban.\n\n"
                "Additionally, if you have any evidence, such as screenshots or chat logs that may support your "
                "case, please include it in your appeal.",
            ),
        ]

        if ticket is not None and ticket.appeal_data:
            a = ticket.appeal_data
            profile = a.profile
            profile_block = (
                f"**[Profile](https://ddnet.org/players/{slugify2(profile.name)})**\n"
                f"Total Points: {profile.points}\n"
                f"Favorite Server: {profile.favorite_server}\n"
                if profile else ""
            )
            items.append(large_seperator())
            items.append(
                discord.ui.TextDisplay(
                    "## Provided Infos\n"
                    "**Public IPv4 Address:**\n"
                    f"```{a.address}```**{a.dnsbl}**\n\n"
                    "**In-game Name:**\n"
                    f"```{a.name}```"
                    f"{profile_block}\n"
                    "**Ban Reason:**\n"
                    f"{a.reason}\n\n"
                    "**Appeal Statement:**\n"
                    f"{a.appeal}"
                )
            )

        self.add_item(discord.ui.Container(*items, accent_colour=TICKET_ACCENT))
