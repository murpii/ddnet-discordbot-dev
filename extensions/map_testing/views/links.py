import discord

from constants import URLs


class ButtonLinks(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        rules = discord.ui.Button(
            label='Mapping Rules',
            style=discord.ButtonStyle.url,  # type: ignore
            url=URLs.DDNET_MAPPING_RULES
        )
        guidelines = discord.ui.Button(
            label='Mapping Guidelines',
            style=discord.ButtonStyle.url,  # type: ignore
            url=URLs.DDNET_MAPPING_GUIDELINES
        )
        self.add_item(rules)
        self.add_item(guidelines)