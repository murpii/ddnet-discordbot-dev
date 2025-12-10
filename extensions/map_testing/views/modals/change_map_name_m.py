import contextlib
import logging
import discord

from extensions.map_testing.cooldown import global_cooldown
from utils.conn import ddnet_delete

log = logging.getLogger("mt")


class CMapNameModal(discord.ui.Modal, title="Change Map Name"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    new_name = discord.ui.TextInput(
        label="The New Map Name",
        placeholder="Back in Time 4",
        max_length=32,
        style=discord.TextStyle.short)  # type: ignore

    async def on_submit(self, interaction: discord.Interaction):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id)  # noqa
        old_filename = map_channel.filename
        await map_channel.update(name=self.new_name.value)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting/CHANGE_NAME",
            string=f"Map name has been changed to: \"{map_channel.name}\"."
        )
        await map_channel.changelog_paginator.update_changelog()

        with contextlib.suppress(RuntimeError):
            await ddnet_delete(self.bot.session, filename=old_filename)
        await interaction.response.send_message(
            f"Changed the map name to `{map_channel.name}`.", ephemeral=True
        )

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"{map_channel.mapper_mentions} The map name has been changed to `{map_channel.name}`.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)
