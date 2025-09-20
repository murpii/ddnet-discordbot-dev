import traceback
import logging
import io

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

    async def report_interaction_error(
            self, interaction: discord.Interaction, error: Exception, note: str = None
    ):
        trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        file = discord.File(io.StringIO(trace), filename="traceback.txt")

        msg = (
                (f"{note}\n" if note else "")
                + f"Error: ```py\n{error}```"
                + f"Initiator: {interaction.user} (ID: {interaction.user.id})\n"
                + "Full traceback attached."
        )

        if dbg_channel := self.bot.get_channel(Channels.DBG):
            await dbg_channel.send(content=msg, file=file)

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "An error occurred. I've notified an administrator. Please try again later.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "An error occurred. I've notified an administrator. Please try again later.",
                ephemeral=True
            )

    async def report_command_error(self, custom_message: str, error: Exception = None, file: discord.File = None):
        """Send a formatted traceback of the error to a specific Discord channel."""
        message = custom_message

        if error is not None:
            trace = traceback.format_exception(type(error), error, error.__traceback__)
            formatted_trace = "".join(trace)

            max_length = 1900
            if len(formatted_trace) > max_length:
                formatted_trace = formatted_trace[-max_length:]
            message = f"⚠️ **Unhandled Exception:** `{type(error).__name__}`\n```\n{formatted_trace}\n```"

        try:
            channel = self.bot.get_channel(Channels.DBG)
            if channel is None:
                channel = await self.bot.fetch_channel(Channels.DBG)
            if file:
                await channel.send(message, file=file)
            else:
                await channel.send(message)
        except Exception as send_error:
            log_traceback(send_error)

    async def dispatch_to_app_command_handler(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if interaction.extras.get("error_handled"):
            return

        await self.on_app_command_error(interaction, error)

    async def on_app_command_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        error_message = error_dict.get(type(error), self.error_message).format(error=error)

        if type(error) not in error_dict:
            log_traceback(error)
            return

        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
        except discord.NotFound:
            log_traceback(error)
        except discord.HTTPException:
            log_traceback(error)

    @commands.Cog.listener()
    async def on_command_error(
            self, ctx: commands.Context[commands.Bot], error: commands.CommandError
    ):
        if isinstance(error, discord.ext.commands.HybridCommandError):
            error = error.original

        error_message = error_dict.get(type(error), self.error_message).format(error=error, ctx=ctx)

        if isinstance(error, commands.CommandNotFound) and ctx.channel.id == Channels.BOT_CMDS:
            return None

        if type(error) not in error_dict:
            return log_traceback(error)

        await ctx.send(
            content=error_message,
            ephemeral=True,
        )
        return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
