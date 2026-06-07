import random

import discord

from constants import Roles
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class ReportContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)

        guild = ticket.channel.guild
        # pull from the staff roles directly instead of scanning every guild member.
        staff = list({
            member
            for role_id in (Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
            if (role := guild.get_role(role_id))
            for member in role.members
        })
        ign = random.choice(staff).display_name if staff else "nameless tee"
        blocker = random.choice(staff).display_name if staff else "brainless tee"

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# [Report Ticket](https://-/)\n"
                f"Hello {ticket.creator.mention}, thanks for reaching out!"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Please follow the steps below to help us handle your report as efficiently as possible!"
                "```prolog\n1. ESC -> Server Info -> Copy Info (in-game).```"
                "```prolog\n2. Paste the copied text into this chat.```"
                "```prolog\n3. Describe the Problem you are having on the server.```",
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "## Example\n"
                "```DDNet GER10 [ger10.ddnet.org whitelist] - Moderate\n"
                "Address: ddnet://37.230.210.231:8320\n"
                f"My IGN: {ign}\n\n"
                f"A player named {blocker} keeps blocking our group! "
                "We have tried ban-voting them but the vote never succeeds.```"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                f"-# NOTE:\n"
                f"-# DO NOT PING <@&{Roles.DISCORD_MODERATOR}> UNLESS YOUR ISSUE IS **DISCORD-SPECIFIC**.\n"
                f"-# THIS ALSO INCLUDES (MASS) PINGING STAFF MEMBERS INDIVIDUALLY."
            ),
            accent_colour=TICKET_ACCENT,
        )
        self.add_item(container)
