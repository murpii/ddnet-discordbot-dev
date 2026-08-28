import contextlib

import discord
from discord.ext import commands

from constants import Channels, Emojis

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


class TesterListeners(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def seed_vote_reactions(self, message: discord.Message):
        if (
                message.type is not discord.MessageType.thread_created
                or message.channel.id != Channels.TESTER_VOTES
        ):
            return

        for emoji_id in (Emojis.F3, Emojis.F4, Emojis.MMM):
            emoji = self.bot.get_emoji(emoji_id)
            if emoji is None:
                continue
            with contextlib.suppress(discord.HTTPException):
                await message.add_reaction(emoji)
