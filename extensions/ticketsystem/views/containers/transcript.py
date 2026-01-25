from typing import Optional

import discord
from discord import SeparatorSpacing

from constants import Emojis
from extensions.ticketsystem.ticket import Ticket


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
                f""
                f"## [ <:ddnet:{Emojis.DDNET}> ] Your {self.ticket.category.value.title()} Transcript"
            ),
            discord.ui.Separator(
                spacing=SeparatorSpacing.large,
                visible=True,
            ),
            discord.ui.TextDisplay(
                'Your ticket has been closed by our staff.'
                if closed_by_staff
                else 'Your ticket has been closed.'
            ),
        ]

        if postscript:
            items.append(
                discord.ui.Separator(
                    spacing=SeparatorSpacing.large,
                    visible=True,
                )
            )
            items.append(
                discord.ui.TextDisplay(
                    "This is the message that has been left for you by our team:\n"
                    f"> {postscript}"
                )
            )

        if transcript_filename:
            items.append(
                discord.ui.Separator(
                    spacing=SeparatorSpacing.large,
                    visible=True,
                )
            )
            items.append(
                discord.ui.TextDisplay("## Transcript:")
            )
            items.append(
                discord.ui.File(
                    f"attachment://{transcript_filename}"
                )
            )

        container = discord.ui.Container(
            *items,
            accent_colour=discord.Colour.ash_embed(),
        )
        self.add_item(container)
