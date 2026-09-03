from typing import TYPE_CHECKING

import discord

from extensions.management.moderator.views.modals.ban import BanModal
from utils.checks import is_staff

if TYPE_CHECKING:
    from bot import DDNet


class BanButton(discord.ui.Button):
    def __init__(self, bot: "DDNet", member: discord.abc.User, *, disabled: bool = False):
        super().__init__(label="Ban", style=discord.ButtonStyle.danger, disabled=disabled)  # noqa
        self.bot = bot
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user, roles="discord_mods"):
            await interaction.response.send_message(
                "Only Discord Moderators can ban.", ephemeral=True
            )
            return

        modal = BanModal(self.bot, self.member)
        await interaction.response.send_modal(modal)
