import discord

# First message accent colour shared by all ticket containers
TICKET_ACCENT = 2210995


def large_seperator() -> discord.ui.Separator:
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True)  # noqa
