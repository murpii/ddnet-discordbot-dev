from typing import Optional

import discord

from constants import Emojis
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import large_seperator


class TranscriptContainer(discord.ui.LayoutView):
    def __init__(
            self,
            ticket: Ticket,
            *,
            closed_by_staff: bool,
            postscript: Optional[str],
            transcript_filename: Optional[str],
    ):
        super().__init__(timeout=None)
        self.ticket = ticket

        items = [
            discord.ui.TextDisplay(
                f"## [ <:ddnet:{Emojis.DDNET}> ] Your {self.ticket.category.value.title()} Transcript"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "Your ticket has been closed by our staff."
                if closed_by_staff
                else "Your ticket has been closed."
            ),
        ]

        if postscript:
            items.append(large_seperator())
            items.append(
                discord.ui.TextDisplay(
                    "This is the message that has been left for you by our team:\n"
                    f"> {postscript}"
                )
            )

        if transcript_filename:
            items.append(large_seperator())
            items.append(discord.ui.TextDisplay("## Transcript:"))
            items.append(discord.ui.File(f"attachment://{transcript_filename}"))
        else:
            items.append(discord.ui.TextDisplay("Transcript not generated: fewer than 2 messages found."))

        self.add_item(discord.ui.Container(*items, accent_colour=discord.Colour.ash_embed()))
