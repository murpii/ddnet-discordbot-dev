#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import zipfile
from io import BytesIO

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from utils.misc import run_process_shell
from utils.text import human_timedelta

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

GH_URL = "https://github.com/murpii/ddnet-discordbot"


class Misc(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None
        self.process = psutil.Process()
        self.start_time = discord.utils.utcnow()

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    @staticmethod
    async def get_latest_commits(num: int = 3) -> str:
        fmt = rf"[`%h`]({GH_URL}/commit/%H) %s (%ar)"
        cmd = f'git log master -{num} --no-merges --format="{fmt}"'
        stdout, _ = await run_process_shell(cmd)
        return stdout

    @app_commands.command(name="about", description="Shows information about the bot")
    async def about(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        channels = sum(len(g.voice_channels + g.text_channels) for g in self.bot.guilds)

        memory = self.process.memory_full_info().uss / 1024 ** 2
        cpu = self.process.cpu_percent() / psutil.cpu_count()
        threads = self.process.num_threads()

        delta = discord.utils.utcnow() - self.start_time
        uptime = human_timedelta(delta.total_seconds(), brief=True)
        latency = self.bot.latency * 1000

        commits = await self.get_latest_commits()

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    "## [Discord bot for DDraceNetwork](https://ddnet.org)",
                    (
                        f"**Stats:** {len(self.bot.guilds)} Guilds, {channels} Channels, "
                        f"{len(self.bot.users)} Users\n"
                        f"**Process:** {memory:.2f} MiB, {cpu:.2f}% CPU, {threads} Threads\n"
                        f"**Bot:** {uptime} Uptime, {latency:.2f}ms Latency"
                    ),
                    accessory=discord.ui.Thumbnail(
                        self.bot.user.display_avatar.with_static_format("png").url
                    ),
                ),
                discord.ui.TextDisplay(
                    f"### Latest commits\n{commits}\n"
                    f"-# Made by jao#3750 with Python (discord.py {discord.__version__})"
                ),
                accent_colour=0xFEA500,
            )
        )

        await interaction.followup.send(view=view)  # noqa

    @app_commands.command(name="avatar", description="Shows the avatar of a user")
    @app_commands.describe(user="@mention the user")
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if user is None:
            user = interaction.user

        if user.avatar is None:
            await interaction.followup.send("User does not have a avatar.")
            return

        try:
            display_avatar = user.display_avatar.url
        except discord.NotFound:
            await interaction.followup.send("Could not get that user's avatar.")
            return

        await interaction.followup.send(display_avatar)

    @app_commands.command(
        name="emojis", description="Returns a zip file with all guild emojis")
    @app_commands.guild_only()
    async def emojis(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        guild = interaction.guild
        if not guild.emojis:
            await interaction.followup.send("This guild doesn't own any emojis")
            return

        count = [0, 0]
        emojis = []  # can't be a dict since emoji names aren't unique
        for emoji in guild.emojis:
            count[emoji.animated] += 1
            ext = "gif" if emoji.animated else "png"
            data = await emoji.read()
            emojis.append((f"{emoji.name}.{ext}", data))

        limit = guild.emoji_limit
        msg = f"Static: {count[0]}/{limit} Animated: {count[1]}/{limit}"

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for emoji in emojis:
                zf.writestr(*emoji)

        buf.seek(0)
        file = discord.File(buf, f"emojis_{guild}.zip")

        await interaction.followup.send(msg, file=file)

        if interaction.response.is_done():  # noqa
            return


async def setup(bot: "DDNet"):
    await bot.add_cog(Misc(bot))
