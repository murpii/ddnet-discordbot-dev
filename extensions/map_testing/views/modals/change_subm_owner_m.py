import logging
import discord

from extensions.map_testing.cooldown import global_cooldown

log = logging.getLogger("mt")


class CSubmissionOwner(discord.ui.Modal, title="Change Submission Owner"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    ident = discord.ui.TextInput(
        label="The users ID.",
        placeholder="Up to 19 digits",
        max_length=19,
        style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        mapper_old = map_channel.mapper_mentions
        user = await self.bot.fetch_user(int(self.ident.value))

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            interaction.user,
            category="MapTesting",
            string=f"\"{map_channel.name}\" ownership has been transferred from "
                   f"{map_channel.mapper_mentions} to \"{user.mention}\"."
        )
        await map_channel.changelog_paginator.update_changelog()
        await map_channel.update(mapper_mentions=user.mention)

        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await interaction.response.send_message(
            f"Changed the submission owner to {map_channel.mapper_mentions}.",
            ephemeral=True)

        # Map channel response
        embed = discord.Embed(
            title=f"",
            description=f"Submission owner changed to {map_channel.mapper_mentions}.",
            color=discord.Color.darker_grey()
        )
        await map_channel.send(embed=embed)