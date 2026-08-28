import discord
from discord.ext import commands

from utils.checks import is_staff

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


async def staff_guard(
        cooldown: commands.CooldownMapping,
        interaction: discord.Interaction,
        roles: list | str = None,
) -> bool:
    """Shared button gate: per-user cooldown + staff role check.
    `roles` narrows the allowed roles, as IDs or a staff_roles() group name"""
    if cooldown.update_rate_limit(interaction):  # noqa
        await interaction.response.send_message(
            "Hey! Don't spam the buttons.", ephemeral=True
        )
        return False

    if not is_staff(interaction.user, roles=roles):
        await interaction.response.send_message(
            "You're missing the required Role to do that!", ephemeral=True
        )
        return False
    return True


class HubButton(discord.ui.Button):
    """Base for the hubs' persistent buttons / subclasses set label/style/id and implement run()."""

    def __init__(self, bot: "DDNet", *, label: str, custom_id: str,
                 style=discord.ButtonStyle.secondary, roles: list | str = None):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.bot = bot
        self.roles = roles

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.roles is not None and not is_staff(interaction.user, roles=self.roles):
            await interaction.response.send_message(
                "You're missing the required Role to do that!", ephemeral=True
            )
            return
        await self.run(interaction)

    async def run(self, interaction: discord.Interaction) -> None:
        raise NotImplementedError
