import discord

from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.text import slugify2


class VpnBanAppealContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket | None = None):
        super().__init__(timeout=None)

        greeting = (
            f"Hello {ticket.creator.mention}, thanks for reaching out!"
            if ticket is not None else "Thanks for reaching out!"
        )

        items = [
            discord.ui.TextDisplay(
                "# [VPN Ban Appeal Ticket](https://-/)\n"
                f"{greeting}"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Your IP was flagged as a VPN, proxy or datacenter connection, which is why you "
                "can't join our servers.\n\n"
                "- If you are using a VPN or proxy, please **disable it** and try again, in most cases "
                "that is all it takes.\n"
                "- If you are **not** using a VPN and believe this is a mistake (e.g. a residential IP "
                "wrongly flagged), explain your situation below and we will look into it.",
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
                    f"{profile_block}"
                )
            )

        self.add_item(discord.ui.Container(*items, accent_colour=TICKET_ACCENT))
