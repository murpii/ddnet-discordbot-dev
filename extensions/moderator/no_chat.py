import logging
import re
import contextlib

import discord
from discord.ext import commands

from constants import Channels

log = logging.getLogger()


class NoChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def robot_cmds(self, message: discord.Message):
        if (
                not message.author.bot
                and message.channel.id == Channels.BOT_CMDS
        ):
            with contextlib.suppress(discord.NotFound):
                await message.delete()

    @commands.Cog.listener("on_message")
    async def playerfinder(self, message: discord.Message):
        if (
                message.channel.id == Channels.PLAYERFINDER
                and message.author != self.bot.user
        ):
            with contextlib.suppress(discord.NotFound):
                await message.delete()

    @commands.Cog.listener("on_message")
    async def media_only(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id == Channels.MEDIA_ONLY:
            has_attachment = bool(message.attachments)
            has_media_embed = any(embed.type in ("image", "video") for embed in message.embeds)
            contains_url = bool(re.compile(r'https?://\S+').search(message.content))

            if not (has_attachment or has_media_embed or contains_url):
                try:
                    await message.delete()
                    try:
                        await message.author.send(
                            f"{message.channel.jump_url}: Only media or links are allowed in this channel.",
                            delete_after=30
                        )
                    except discord.Forbidden:
                        await message.channel.send(
                            f"{message.author.mention} Only media or links are allowed in this channel.",
                            delete_after=5
                        )
                except discord.Forbidden:
                    log.error("media_only: Missing permissions to delete messages.")
                return
