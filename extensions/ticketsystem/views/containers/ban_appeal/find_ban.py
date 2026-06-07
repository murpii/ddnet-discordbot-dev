import discord

from extensions.ticketsystem.views.containers.base import large_seperator


class FindBanContainer(discord.ui.LayoutView):
    """Ephemeral result of the "Find Ban" button: bans grouped by in-game name."""

    def __init__(self, address: str, grouped_bans: dict[str, list[str]], total_bans: int):
        super().__init__(timeout=None)

        title = "One ban" if total_bans == 1 else f"{total_bans} bans"
        items = [discord.ui.TextDisplay(f"## {title} found for IP `{address}`")]

        if total_bans == 0:
            items.append(
                discord.ui.TextDisplay("Could not parse any valid ban messages or database bans.")
            )
        else:
            for name, entries in grouped_bans.items():
                items.append(large_seperator())
                value = "\n\n".join(entries)[:1024]
                items.append(discord.ui.TextDisplay(f"**NAME: {name}**\n{value}"))

        self.add_item(discord.ui.Container(*items, accent_colour=discord.Colour.red()))
