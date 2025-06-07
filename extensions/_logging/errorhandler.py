import traceback
import logging

import discord
from discord import app_commands
from discord.ext import commands

from constants import Channels

log = logging.getLogger()

# Custom error handling mappings and messages.
error_dict = {
    # app_commands
    app_commands.AppCommandError: "An error occurred: {error}",
    app_commands.MissingRole: "You are missing the role required to use this command.",
    app_commands.MissingAnyRole: "You are missing some roles required to use this command.",
    app_commands.MissingPermissions: "You are missing the required permissions to use this command.",
    app_commands.CheckFailure: "You are not allowed to use this command.",
    app_commands.CommandOnCooldown: "This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
    app_commands.BotMissingPermissions: "The bot is missing the required permissions to use this command.",
    app_commands.CommandSignatureMismatch: "The command signature does not match: {error}",
    # hybrid commands
    commands.CommandError: "An error occurred: {error}",
    commands.HybridCommandError: "A hybrid command error occurred: {error}",
    commands.ConversionError: "An error occurred during conversion: {error}",
    commands.MissingRole: "You are missing the role required to use this command.",
    commands.MissingAnyRole: "You are missing some roles required to use this command.",
    commands.MissingPermissions: "You are missing the required permissions to use this command.",
    commands.CheckFailure: "You are not allowed to use this command.",
    commands.CommandNotFound: "This command was not found.",
    commands.CommandOnCooldown: "This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
    commands.BadArgument: "Invalid argument passed. Correct usage:\n```{ctx.command.usage}```",
    commands.MissingRequiredArgument: "Missing required argument. Correct usage:\n```{ctx.command.usage}```",
    commands.MissingRequiredAttachment: "Missing required attachment.",
    commands.NotOwner: "You are not the owner of this bot.",
    commands.BotMissingPermissions: "The bot is missing the required permissions to use this command.",
}


def log_traceback(error: Exception):
    trace = traceback.format_exception(None, error, error.__traceback__)
    formatted_trace = "".join(trace)

    log.exception(f"Error: {error}\n" f"Traceback:\n" f"{formatted_trace}")


class ErrorHandler(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.error_message = "An error occurred. Please try again later."
        bot.tree.error(self.dispatch_to_app_command_handler)

    async def dispatch_to_app_command_handler(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if interaction.extras.get("error_handled"):
            return

        await self.on_app_command_error(interaction, error)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        error_message = error_dict.get(type(error), self.error_message).format(error=error)  # noqa

        if type(error) not in error_dict:
            log_traceback(error)
            return

        if interaction.response.is_done():  # noqa
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(  # noqa
                error_message, ephemeral=True
            )

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context[commands.Bot], error: commands.CommandError
    ):
        if isinstance(error, discord.ext.commands.HybridCommandError):
            error = error.original

        error_message = error_dict.get(type(error), self.error_message).format(error=error, ctx=ctx)  # noqa

        if isinstance(error, commands.CommandNotFound) and ctx.channel.id == Channels.BOT_CMDS:
            return

        if type(error) not in error_dict:
            return log_traceback(error)

        await ctx.send(
            content=error_message,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
