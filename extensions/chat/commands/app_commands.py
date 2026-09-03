import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds

if TYPE_CHECKING:
    from bot import DDNet


class Botscribe(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

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
