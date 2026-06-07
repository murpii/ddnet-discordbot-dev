import discord
from discord.ui import Button


class ChoiceView(discord.ui.View):
    def __init__(self, bot, end, start=None):
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
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have the necessary permissions to purge messages."
            )
            return

        await interaction.edit_original_response(content=f"Deleted {len(deleted)} messages.")

    @discord.ui.button(label="Abort", style=discord.ButtonStyle.red, custom_id="Abort:purge")
    async def cancel(self, _: discord.Interaction):
        self.stop()
