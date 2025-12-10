import discord

from extensions.moderator.views.modals.timeout import TimeoutModal


class TimeoutButton(discord.ui.Button):
    def __init__(self, bot, member: discord.Member):
        super().__init__(label="Timeout", style=discord.ButtonStyle.primary)  # noqa
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.member, discord.Member):
            await interaction.response.send_message(
                "Cannot timeout: target is not a guild member.",
                ephemeral=True,
            )
            return

        modal = TimeoutModal(self.bot, self.member)
        await interaction.response.send_modal(modal)
