import discord

from utils.checks import is_staff
from extensions.management.moderator.views.modals.kick import KickModal


class KickButton(discord.ui.Button):
    def __init__(self, bot, member: discord.Member, *, disabled: bool = False):
        super().__init__(label="Kick", style=discord.ButtonStyle.secondary, disabled=disabled)  # noqa
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user, roles="discord_mods"):
            await interaction.response.send_message(
                "Only Discord Moderators can kick.", ephemeral=True
            )
            return

        if not isinstance(self.member, discord.Member):
            await interaction.response.send_message(
                "Cannot kick: target is not a guild member.",
                ephemeral=True,
            )
            return

        modal = KickModal(self.bot, self.member)
        await interaction.response.send_modal(modal)
