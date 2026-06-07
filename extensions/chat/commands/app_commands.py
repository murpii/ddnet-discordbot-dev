import contextlib
import re
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands

from extensions.chat.views.echo_modal import EchoModal
from extensions.chat.views.edit_modal import EditMsgModal
from utils.checks import ddnet_only
from constants import Guilds


class Botscribe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="echo", description="Echo a message via bot")
    async def echo_command(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EchoModal(interaction.channel))

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="by_id", description="Edit a message by ID")
    @app_commands.describe(message_id="Message ID to edit")
    async def by_id(self, interaction: discord.Interaction, message_id: str):
        try:
            message = await interaction.channel.fetch_message(int(message_id))
        except (ValueError, discord.NotFound):
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return

        await interaction.response.send_modal(EditMsgModal(message))

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="less",
        description="Reads the raw message content and echos it back")
    @app_commands.describe(
        message_id="The message ID of the discord message",
        encase_urls="Whether URLs in the message content should be encased in angle brackets")
    async def less(
            self,
            interaction: discord.Interaction,
            message_id: str,
            encase_urls: bool = False,
            escape_markdown: bool = False
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            message = await interaction.channel.fetch_message(int(message_id))
            message_fmt = message.content
            if escape_markdown:
                message_fmt = discord.utils.escape_markdown(message.content)
            if encase_urls:
                message_fmt = re.sub(r'(https://[^\s)]+)', r'<\1>', message_fmt)
            await interaction.followup.send(f"```{message_fmt}```")
        except discord.NotFound:
            await interaction.followup.send(
                content="Could not find the mentioned message. "
                        "Ensure the command is used in the same channel as the message you're trying to fetch."
            )
