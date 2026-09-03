import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import forbidden_report

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

# Custom error handling mappings and messages.
error_dict = {
    # app_commands
    app_commands.AppCommandError: "An error occurred: {error}",
    app_commands.CommandInvokeError: "An error occurred: {error}",
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
    # general
    discord.Forbidden: "I cannot perform that action: {error}",
    discord.NotFound: "The resource I tried to access was not found: {error}",
    discord.HTTPException: "An HTTP error occurred while trying to perform the action: {error}",
}


def unwrap_error(error: Exception) -> Exception:
    while True:
        original = getattr(error, "original", None)
        if original is not None:
            error = original
            continue

        cause = getattr(error, "__cause__", None)
        if cause is not None:
            error = cause
            continue

        return error


def build_message(error: Exception, fallback: str, channel=None, **fields) -> str:
    """The message shown to the user for an error.

    The real cause is looked up first, since app commands wrap everything in a
    CommandInvokeError and that would otherwise hide the mapping. A Forbidden
    also gets a report of which permission the blocked request needed.
    """
    real_error = unwrap_error(error)
    template = error_dict.get(type(real_error)) or error_dict.get(type(error)) or fallback
    message = template.format(error=real_error, **fields)

    if isinstance(real_error, discord.Forbidden):
        report = forbidden_report(real_error, channel)
        if report:
            message = f"{message}\n{report}"

    return message


# Full trace
def log_traceback(error: Exception):
    real_error = unwrap_error(error)

    log.error(
        "Unhandled exception: %s: %s",
        type(real_error).__name__,
        real_error,
        exc_info=(type(real_error), real_error, real_error.__traceback__),
    )


class ErrorHandler(commands.Cog):
    def __init__(self, bot: "DDNet") -> None:
        self.bot = bot
        self.error_message = "An error occurred. Please try again later."
        bot.tree.error(self.dispatch_to_app_command_handler)

    # TODO: Just some testing


    async def dispatch_to_app_command_handler(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if interaction.extras.get("error_handled"):
            return

        await self.on_app_command_error(interaction, error)

    async def on_app_command_error(self, interaction, error):
        wrapped_error = error
        error_message = build_message(error, self.error_message, interaction.channel)

        with contextlib.suppress(discord.Forbidden, discord.HTTPException, discord.NotFound):
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)

        log_traceback(wrapped_error)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context[commands.Bot], error: commands.CommandError):
        wrapped_error = error

        if isinstance(wrapped_error, commands.CommandNotFound):
            return

        error_message = build_message(error, self.error_message, ctx.channel, ctx=ctx)

        log_traceback(wrapped_error)

        if type(unwrap_error(error)) not in error_dict and type(error) not in error_dict:
            return

        await ctx.send(content=error_message, ephemeral=True)


async def setup(bot: "DDNet") -> None:
    await bot.add_cog(ErrorHandler(bot))
