import discord

from extensions.map_testing.cooldown import global_cooldown
from utils.text import slugify2


class CMappersModal(discord.ui.Modal, title="Change Mappers"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    mappers = discord.ui.TextInput(
        label="Mappers",
        placeholder="Example: Welf, louis, Pipou, Ravie",
        max_length=64,
        style=discord.TextStyle.short
    )

    @staticmethod
    def get_mapper_urls(mappers: list) -> list:
        return [
            f"[{mapper}](https://ddnet.org/mappers/{slugify2(mapper)})"
            for mapper in mappers
        ]

    async def on_submit(self, interaction: discord.Interaction):
        mappers_list = [mapper.strip() for mapper in self.mappers.value.split(",")]
        mapper_urls = self.get_mapper_urls(mappers_list)
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)
        await map_channel.update(mappers=mappers_list)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/CHANGE_MAPPERS",
            string=f'Mappers has been changed to: {", ".join(mapper_urls)}.',
        )
        await map_channel.changelog_paginator.update_changelog()

        await interaction.response.send_message(
            f'Changed the mapper(s) to {", ".join(mapper_urls)}.',
            ephemeral=True
        )

        embed = discord.Embed(
            title=f"",
            description=f'{map_channel.mapper_mentions} Changed the mapper(s) to {", ".join(mapper_urls)}.',
            color=discord.Color.darker_grey(),
        )
        await map_channel.send(embed=embed)
