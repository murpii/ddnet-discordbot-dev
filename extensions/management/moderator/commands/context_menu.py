import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds
from utils.checks import staff_roles
from extensions.management.moderator.views.modals.ban import BanModal
from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


class ModeratorCtxMenu(commands.Cog):
    def __init__(self, bot: "DDNet") -> None:
        self.bot = bot
        self.guild = discord.Object(Guilds.DDNET)

        self.ban_user_ctx_menu = app_commands.ContextMenu(
            name="Ban user",
            callback=self.ban_user_context_menu,
            type=discord.AppCommandType.user,  # noqa
        )
        self.bot.tree.add_command(self.ban_user_ctx_menu, guild=self.guild)

        self.user_info_ctx_menu = app_commands.ContextMenu(
            name="User info",
            callback=self.user_info_context_menu,
            type=discord.AppCommandType.user,  # noqa
        )
        self.bot.tree.add_command(self.user_info_ctx_menu, guild=self.guild)

    async def cog_unload(self) -> None:
        for menu in (self.ban_user_ctx_menu, self.user_info_ctx_menu):
            self.bot.tree.remove_command(menu.name, guild=self.guild, type=menu.type)

    @app_commands.checks.has_any_role(*staff_roles("discord_mods"))
    async def ban_user_context_menu(
            self,
            interaction: discord.Interaction,
            user: discord.User,
    ) -> None:
        modal = BanModal(self.bot, member=user)
        await interaction.response.send_modal(modal)

    @app_commands.checks.has_any_role(*staff_roles("mods"))
    async def user_info_context_menu(
            self,
            interaction: discord.Interaction,
            user: discord.User,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        info = await self.bot.moddb.fetch_user_info(user)

        if not info:
            await interaction.followup.send(view=NoUserInfoView(), ephemeral=True)
            return

        await interaction.followup.send(
            view=UserInfoView(self.bot, info, interaction.user), ephemeral=True
        )


async def setup(bot: "DDNet") -> None:
    await bot.add_cog(ModeratorCtxMenu(bot))
