import discord
from discord.ext import commands
from discord import app_commands

from utils.checks import is_staff

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

MAX_FIELD_LENGTH = 1024
MAX_FIELDS = 25


class HelpFormatter:
    @staticmethod
    def format_command(command: app_commands.Command) -> str:
        params = " ".join(f"<{param.name}>" for param in command.parameters if param.required)
        line = f"/{command.qualified_name} {params}".strip()
        return f"`{line}`"

    @staticmethod
    def can_run(command: app_commands.Command, user) -> bool:
        top = command.root_parent or command
        needed = top.default_permissions
        group = getattr(command.callback, "__staff_group__", None)

        if not isinstance(user, discord.Member):
            return needed is None and group is None
        if needed is not None and not user.guild_permissions.is_superset(needed):
            return False
        return group is None or is_staff(user, roles=group)

    @classmethod
    def collect_commands(cls, bot: "DDNet", interaction: discord.Interaction) -> dict:
        found = list(bot.tree.walk_commands())
        if interaction.guild is not None:
            found += bot.tree.walk_commands(guild=interaction.guild)

        grouped = {}
        for command in found:
            if isinstance(command, app_commands.Group):
                continue  # the group itself has nothing to run, only its subcommands do
            if not cls.can_run(command, interaction.user):
                continue
            grouped.setdefault(command.binding, []).append(command)

        for commands_list in grouped.values():
            commands_list.sort(key=lambda cmd: cmd.qualified_name)
        return grouped

    @classmethod
    def build_embed(cls, bot: "DDNet", interaction: discord.Interaction) -> discord.Embed:
        embed = discord.Embed(
            title="Commands",
            description="Available slash commands",
            colour=discord.Colour.blurple(),
        )

        for cog, commands_list in list(cls.collect_commands(bot, interaction).items())[:MAX_FIELDS]:
            name = getattr(cog, "qualified_name", None) or "Other"
            value = "\n".join(cls.format_command(command) for command in commands_list)

            if description := getattr(cog, "description", None):
                value = f"> {description.strip()}\n\n{value}"

            embed.add_field(name=name, value=value[:MAX_FIELD_LENGTH], inline=False)

        return embed


class HelpAppCommand(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

    @app_commands.command(name="help", description="Show available commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = HelpFormatter.build_embed(self.bot, interaction)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "DDNet"):
    await bot.add_cog(HelpAppCommand(bot))
