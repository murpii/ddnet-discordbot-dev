import discord
from discord import app_commands, ui
from discord.ext import commands

from extensions.moderator.views.modals.ban import BanModal


class ModeratorCtxMenu(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        self.ban_user_ctx_menu = app_commands.ContextMenu(
            name="Ban user",
            callback=self.ban_user_context_menu,
            type=discord.AppCommandType.user,  # noqa
        )
        self.bot.tree.add_command(self.ban_user_ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.ban_user_ctx_menu.name,
            type=self.ban_user_ctx_menu.type,
        )

    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_user_context_menu(
            self,
            interaction: discord.Interaction,
            user: discord.User,
    ) -> None:
        modal = BanModal(self.bot, member=user)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModeratorCtxMenu(bot))
