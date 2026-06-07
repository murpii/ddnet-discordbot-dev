import discord
from discord.ext import commands
from discord.ui import Button

from extensions.management.hub import staff_guard
from extensions.management.moderator.views.containers.mod_log import open_user_info_panel


class ModeratorInfoButtons(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction)

    @discord.ui.button(
        label="User Info",
        style=discord.ButtonStyle.green,  # noqa
        custom_id="Moderation:info",
    )
    async def mod_info(self, interaction: discord.Interaction, _: Button):
        await open_user_info_panel(self.bot, interaction)
