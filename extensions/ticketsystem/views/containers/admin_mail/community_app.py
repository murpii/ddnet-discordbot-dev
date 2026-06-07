import discord

from constants import URLs, Channels
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class CommunityAppContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        rules_btn = discord.ui.Button(
            label="Master Server Rules",
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_MASTER_RULES,
        )
        community_btn = discord.ui.Button(
            label="Community Rules",
            style=discord.ButtonStyle.url,
            url=URLs.DDNET_COMMUNITY_RULES,
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Community Application](https://-/)"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Before applying, make sure your community:\n"
                "- Fully complies with the Master Server Rules\n"
                "- Follows all Community Rules\n"
                "- Meets all required criteria\n\n"
            ),
            discord.ui.ActionRow(rules_btn, community_btn),
            discord.ui.TextDisplay(
                "Applications that do not meet these requirements will rejected."
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                f"-# **Note:** For technical issues, use <#{Channels.QUESTIONS}> or <#{Channels.BUGS}> instead."
            ),
            accent_colour=TICKET_ACCENT,
        )

        self.add_item(container)
