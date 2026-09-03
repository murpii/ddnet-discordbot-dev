from typing import TYPE_CHECKING

import discord
from discord.ui import Button

from utils.checks import forbidden_report

if TYPE_CHECKING:
    from bot import DDNet


class ChoiceView(discord.ui.View):
    def __init__(self, bot: "DDNet", end, start=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.end = end
        self.start = start

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green, custom_id="Continue:purge")
    async def confirm(self, interaction: discord.Interaction, _: Button):
        self.stop()
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            await interaction.followup.send(
                "Purging... This might take awhile.",
            )
            deleted = await interaction.channel.purge(
                limit=None, after=self.end, before=self.start, reason="Purge"
            )
        except discord.Forbidden as error:
            report = forbidden_report(error, interaction.channel)
            await interaction.followup.send(f"I can't purge messages here.\n{report}")
            return

        await interaction.edit_original_response(content=f"Deleted {len(deleted)} messages.")

    @discord.ui.button(label="Abort", style=discord.ButtonStyle.red, custom_id="Abort:purge")
    async def cancel(self, _: discord.Interaction):
        self.stop()
