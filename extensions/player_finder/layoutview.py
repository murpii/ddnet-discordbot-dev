import discord
from discord import SeparatorSpacing


class PlayerfinderView(discord.ui.LayoutView):
    container = discord.ui.Container(
        discord.ui.TextDisplay(""),
        discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),  # noqa
        discord.ui.TextDisplay("Placeholder"),
    )
