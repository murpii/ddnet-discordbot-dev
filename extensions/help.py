import discord
from discord.ext import commands
from discord import app_commands

from constants import Channels


class HelpCommand(commands.MinimalHelpCommand):
    async def send_bot_help(self, mapping):
        """Shows a list of public commands"""

        if self.context.channel.id == Channels.BOT_CMDS:
            return

        excluded_cogs = ["Help", "Moderation", "Botscribe", "Forum", "TestingBans", ]
        excluded_commands = ["$wikicontributor <member>"]

        embed = discord.Embed(title="Available Text-based Commands")
        embed.colour = discord.Colour.blurple()

        for cog, commands in mapping.items():
            if cog is None or cog.qualified_name in excluded_cogs:
                continue

            filtered_commands = []
            for command in commands:
                if self.get_command_signature(command) not in excluded_commands:
                    # Get the command name and its aliases
                    command_signature = self.get_command_signature(command)
                    if command.aliases:
                        aliases = [f"${alias}" for alias in command.aliases]
                        command_signature += f" (**Aliases**: {', '.join(aliases)})"
                    filtered_commands.append(command_signature)

            if filtered_commands:
                cog_name = getattr(cog, "qualified_name", "No Category")
                embed.add_field(name=cog_name, value="\n".join(filtered_commands), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)


class HelpAppCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows available commands")
    async def help_command(self, interaction: discord.Interaction):
        """Shows a list of public commands"""

        excluded_cogs = ["Help", "Moderation", "Botscribe", "Forum"]
        excluded_commands = ["$wikicontributor <member>"]

        embed = discord.Embed(title="Available Text-based Commands")
        mapping = self.bot.cogs  # Adjust based on your structure

        for cog_name, cog in mapping.items():
            if cog_name in excluded_cogs:
                continue

            filtered_commands = []
            for command in cog.get_commands():  # Get the commands from the cog
                if self.get_command_signature(command) not in excluded_commands:
                    command_signature = f"**$**{self.get_command_signature(command)}"  # Add "$" in front
                    if command.aliases:
                        aliases = [f"**$**{alias}" for alias in command.aliases]
                        command_signature += f" (**Aliases**: {', '.join(aliases)})"
                    filtered_commands.append(command_signature)

            if filtered_commands:
                embed.add_field(name=cog_name, value="\n".join(filtered_commands), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)  # noqa

    @staticmethod
    def get_command_signature(command):
        """Get the command signature."""
        return f"{command.qualified_name} " + " ".join(
            f"<{arg}>" for arg in command.clean_params
        )

async def setup(bot):
    await bot.add_cog(HelpAppCommand(bot))
