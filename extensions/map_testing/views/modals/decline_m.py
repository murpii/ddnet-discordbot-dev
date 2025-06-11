import logging
import discord

from extensions.map_testing.map_channel import MapState
from extensions.map_testing.cooldown import global_cooldown
from extensions.map_testing.scores import add_score


log = logging.getLogger("mt")


class DeclineReasonModal(discord.ui.Modal, title="Decline Reason"):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    decline_reason = discord.ui.TextInput(
        label="Your Decline Reason",
        placeholder="You can leave this blank. The modal exist so you can provide the decline reason anonymously.",
        max_length=500,
        required=False,
        style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa
        map_channel = self.bot.map_channels.get(interaction.channel.parent.id) # noqa
        await map_channel.set_state(state=MapState.DECLINED)
        global_cooldown.update_cooldown(interaction.channel.parent.id)

        await map_channel.changelog_paginator.add_changelog(
            map_channel,
            self.bot.user if self.decline_reason.value == "" else interaction.user,
            category="MapTesting/DECLINE",
            string=f"\"{map_channel.name}\" has been DECLINED."
        )
        await map_channel.changelog_paginator.update_changelog()

        await interaction.followup.send(
            content=f"Declined submission \"{map_channel.name}\" successfully..",
            ephemeral=True
        )

        embed = discord.Embed(
            title="Submission has been declined.",
            description=f"{map_channel.mapper_mentions}\nUnfortunately, your map submission has been declined. "
                        "Don't worry though—take a look at the feedback from our Testers, and consider playing "
                        "our latest releases to gain more experience and better understanding what we're looking for!\n\n"
        )

        if self.decline_reason.value:
            embed.add_field(
                name="The reason provided:",
                value=self.decline_reason.value,
                inline=False
            )

        # Map channel response
        await map_channel.send(content=f"Mention: {map_channel.mapper_mentions}", embed=embed)

        add_score(interaction.user.id, "DECLINED")

        log.info("%s declined submission #%s", interaction.user, interaction.channel)