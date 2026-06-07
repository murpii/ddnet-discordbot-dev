import discord

from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class GateContainer(discord.ui.LayoutView):
    """A simple title + description notice (no buttons)."""

    def __init__(self, title: str, description: str, accent_colour: discord.Colour | int):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}"),
                large_seperator(),
                discord.ui.TextDisplay(description),
                accent_colour=accent_colour,
            )
        )


class NoticeContainer(discord.ui.LayoutView):
    """A bare one line notice, used to replace a confirm prompt once it's resolved."""

    def __init__(self, text: str, accent_colour: discord.Colour | int = TICKET_ACCENT):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_colour=accent_colour,
            )
        )
