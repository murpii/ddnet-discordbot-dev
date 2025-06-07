#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from io import BytesIO
from typing import List, Union

import discord
from PIL import Image, ImageDraw, ImageFont
from discord import app_commands
from discord.ext import commands

from utils.image import save, wrap_new
from constants import Emojis, Channels

DIR = "data/assets"


def wrap(font: ImageFont, text: str, line_width: int) -> str:
    words = text.split()

    lines = []
    line = []

    for word in words:
        newline = " ".join(line + [word])

        left, top, right, bottom = font.getbbox(newline)
        w, _ = right - left, bottom

        if w > line_width:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)

    if line:
        lines.append(" ".join(line))

    wrapped_text = "\n".join(lines)
    return wrapped_text.strip()


def check_text_length(text1: str, text2: str = None, max_chars: int = 110) -> List[str]:
    errors = []
    if text1 and len(text1) > max_chars:
        errors.append("Text-1 has too many characters")
    if text2 and len(text2) > max_chars:
        errors.append("Text-2 has too many characters")
    return errors


async def render(name: str, text1: str, text2: str = None) -> BytesIO:
    base = Image.open(f"{DIR}/memes/{name}.png")
    canv = ImageDraw.Draw(base)
    font = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 46)

    canv.text((570, 70), wrap(font, text1, 400), fill="black", font=font)
    if text2 is not None:
        canv.text((570, 540), wrap(font, text2, 400), fill="black", font=font)

    return save(base)


async def render_teebob(text: str) -> BytesIO:
    base = Image.open(f"{DIR}/memes/teebob.png")
    canv = ImageDraw.Draw(base)
    font = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 40)

    box = ((100, 110), (360, 370))
    wrap_new(canv, box, text, font=font)

    return save(base)


async def render_clown(text1: str, text2: str, text3: str, text4: str) -> BytesIO:
    base = Image.open(f"{DIR}/memes/clown.png")
    canv = ImageDraw.Draw(base)
    font = ImageFont.truetype(f"{DIR}/fonts/normal.ttf", 30)

    canv.text((10, 10), wrap(font, text1, 310), fill="black", font=font)
    canv.text((10, 180), wrap(font, text2, 310), fill="black", font=font)
    canv.text((10, 360), wrap(font, text3, 310), fill="black", font=font)
    canv.text((10, 530), wrap(font, text4, 310), fill="black", font=font)

    return save(base)


class Memes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="angry", description="Renders a angry emote meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text1")
    async def angry_command(
        self, interaction: discord.Interaction, text1: str, text2: str = None
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if errors := check_text_length(text1, text2):
            for error in errors:
                await interaction.channel.send(error)
            return
        buf = await render("angry", text1, text2)
        file = discord.File(buf, filename="angry.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="drake", description="Renders a drake meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text1")
    async def drake_command(
        self, interaction: discord.Interaction, text1: str, text2: str
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if errors := check_text_length(text1, text2):
            for error in errors:
                await interaction.followup.send(error)
            return
        buf = await render("drake", text1, text2)
        file = discord.File(buf, filename="drake.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="happy", description="Renders a happy emote meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text1")
    async def happy_command(
        self, interaction: discord.Interaction, text1: str, text2: str = None
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if errors := check_text_length(text1, text2):
            for error in errors:
                await interaction.followup.send(error)
            return
        buf = await render("happy", text1, text2)
        file = discord.File(buf, filename="happy.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="sleep", description="Renders a sleep emote meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text1")
    async def sleep_command(
        self, interaction: discord.Interaction, text1: str, text2: str = None
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if errors := check_text_length(text1, text2):
            for error in errors:
                await interaction.followup.send(error)
            return
        buf = await render("sleep", text1, text2)
        file = discord.File(buf, filename="sleep.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="teeward", description="Renders a teeward meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text2")
    async def teeward_command(
        self, interaction: discord.Interaction, text1: str, text2: str
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if errors := check_text_length(text1, text2):
            for error in errors:
                await interaction.followup.send(error)
            return
        buf = await render("teeward", text1, text2)
        file = discord.File(buf, filename="teeward.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="teebob", description="Renders a teebob meme with given text"
    )
    @app_commands.describe(text="text1")
    async def teebob(self, interaction: discord.Interaction, *, text: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        buf = await render_teebob(text)
        file = discord.File(buf, filename="teebob.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(
        name="clown", description="Renders a clown meme with given text"
    )
    @app_commands.describe(text1="text1", text2="text2", text3="text3", text4="text4")
    async def clown(
        self,
        interaction: discord.Interaction,
        text1: str,
        text2: str,
        text3: str,
        text4: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        buf = await render_clown(text1, text2, text3, text4)
        file = discord.File(buf, filename="clown.png")
        await interaction.followup.send(file=file)

        if interaction.response.is_done():  # noqa
            return


class Votes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._votes = {}

    # def get_emoji(self, name):
    #     return discord.utils.get(self.bot.emojis, name=name)

    @commands.Cog.listener()
    async def on_reaction_add(
        self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]
    ):
        if user.bot:
            return

        message = reaction.message
        if message.id not in self._votes:
            return

        emoji = reaction.emoji
        if emoji == self.bot.get_emoji(Emojis.F3):
            self._votes[message.id] += 1
        elif emoji == self.bot.get_emoji(Emojis.F4):
            self._votes[message.id] -= 1
        else:
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                return

    @commands.Cog.listener()
    async def on_reaction_remove(
        self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]
    ):
        if user.bot:
            return

        message = reaction.message
        if message.id not in self._votes:
            return

        emoji = reaction.emoji
        if emoji == self.bot.get_emoji(Emojis.F3):
            self._votes[message.id] -= 1
        elif emoji == self.bot.get_emoji(Emojis.F3):
            self._votes[message.id] += 1

    @commands.Cog.listener()
    async def on_reaction_clear(self, message: discord.Message, _):
        if message.id not in self._votes:
            return

        self._votes[message.id] = 0

    async def _kick(
        self, interaction: discord.Interaction, user: discord.Member, reason: str
    ) -> tuple:
        reason = reason or "No reason given"
        msg = (
            f"{interaction.user.display_name} called for vote to kick {user} ({reason})"
        )
        await interaction.response.send_message(msg)  # noqa
        message = await interaction.original_response()

        self._votes[message.id] = 0

        await message.add_reaction(self.bot.get_emoji(Emojis.F3))
        await message.add_reaction(self.bot.get_emoji(Emojis.F4))

        i = 30
        while i >= 0:
            await message.edit(content=f"{msg} — {i}s left")

            # update countdown only every 5 seconds at first to avoid being rate limited
            seconds = 5 if i > 5 else 1
            i -= seconds
            await asyncio.sleep(seconds)

        result = self._votes.pop(message.id, 0)
        result_msg = (
            f"Vote passed. {user} kicked by vote ({reason})"
            if result > 0
            else "Vote failed"
        )

        return result, result_msg

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 30, key=None)
    @app_commands.command(name="vote-kick", description="Initiates a kick-vote")
    async def vote_kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        *,
        reason: str = None,
    ):
        if interaction.channel.id == Channels.BOT_CMDS:
            await interaction.response.send_message(  # noqa
                content="You can use this command anywhere but here.",
                ephemeral=True)
            return
        _, result_msg = await self._kick(interaction, user, reason)
        await interaction.followup.send(result_msg)

    @vote_kick.error
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        async def send(content: str):
            if interaction.response.is_done():  # noqa
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)  # noqa

        if isinstance(error, app_commands.CommandOnCooldown):
            await send(
                f"This command is on cooldown. Try again in {error.retry_after:.2f}s"
            )
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Memes(bot))
    await bot.add_cog(Votes(bot))
