#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import zipfile
from datetime import datetime, timedelta
from io import BytesIO

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from constants import Emojis
from datetime import timezone
from utils.misc import run_process_shell
from utils.text import human_timedelta

log = logging.getLogger(__name__)

GH_URL = "https://github.com/murpii/ddnet-discordbot"


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.process = psutil.Process()
        self.start_time = discord.utils.utcnow()
        self.api_key = self.bot.config.get("WEATHER_API", "KEY")

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

        title = "Discord bot for DDraceNetwork"
        embed = discord.Embed(title=title, color=0xFEA500, url="https://ddnet.org")

        embed.set_author(
            name=self.bot.user,
            icon_url=self.bot.user.display_avatar.with_static_format("png"),
        )

        channels = sum(len(g.voice_channels + g.text_channels) for g in self.bot.guilds)
        stats = f"{len(self.bot.guilds)} Guilds\n{channels} Channels\n{len(self.bot.users)} Users"
        embed.add_field(name="Stats", value=stats)

        memory = self.process.memory_full_info().uss / 1024 ** 2
        cpu = self.process.cpu_percent() / psutil.cpu_count()
        threads = self.process.num_threads()
        embed.add_field(
            name="Process", value=f"{memory:.2f} MiB\n{cpu:.2f}% CPU\n{threads} Threads"
        )

        delta = discord.utils.utcnow() - self.start_time
        uptime = human_timedelta(delta.total_seconds(), brief=True)
        latency = self.bot.latency * 1000
        embed.add_field(name="Bot", value=f"{uptime} Uptime\n{latency:.2f}ms Latency")

        commits = await self.get_latest_commits()
        embed.add_field(name="Latest commits", value=commits)

        embed.set_footer(
            text=f"Made by jao#3750 with Python (discord.py {discord.__version__})"
        )

        await interaction.followup.send(embed=embed)  # noqa

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(name="commandstats", description="Shows command stats")
    async def commandstats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        query = "SELECT command, COUNT(*) AS uses FROM discordbot_stats_commands GROUP BY command ORDER BY uses DESC;"
        stats = await self.bot.fetch(query, fetchall=True)
        stats = [s for s in stats if self.bot.walk_commands() is not None]

        width = len(max((s[0] for s in stats[:20]), key=len))
        desc = "\n".join(f'`/{c}{"." * (width - len(c))}:` {u}' for c, u in stats[:20])
        total = sum(s[1] for s in stats)

        embed = discord.Embed(
            title="Command Stats", description=desc, color=discord.Color.blurple()
        )
        embed.set_footer(text=f"{total} total")

        await interaction.followup.send(embed=embed)

        if interaction.response.is_done():  # noqa
            return

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

    async def fetch_weather_data(self, city: str) -> dict:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"APPID": self.api_key, "q": city, "units": "metric"}

        async with self.session.get(url, params=params) as resp:
            js = await resp.json()
            if resp.status == 200:
                return js
            if resp.status == 404:
                raise ValueError(f'City "{city}" not found.')

            fmt = "Failed to fetch weather data for city %r: %s (status code: %d %s)"
            log.error(fmt, city, js["message"], resp.status, resp.reason)
            raise RuntimeError("Could not fetch weather information")

    @app_commands.command(
        name="weather", description="Show weather information of a city"
    )
    @app_commands.describe(
        city="Enter the city for which you'd like to view the weather information."
    )
    async def weather(self, interaction: discord.Interaction, *, city: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        try:
            data = await self.fetch_weather_data(city)
        except Exception as exc:
            await interaction.followup.send(exc)
            return

        city = data["name"]
        country = data["sys"].get("country")
        condition = data["weather"][0]["id"]
        description = data["weather"][0]["description"]
        temp = data["main"]["temp"]  # °C
        feels_like = data["main"]["feels_like"]  # °C
        wind = data["wind"]["speed"]  # m/s
        humidity = data["main"]["humidity"]  # %
        cloudiness = data["clouds"]["all"]  # %

        if country is None:
            flag = f"<:flag_unk:{Emojis.FLAG_UNK}>"
        else:
            flag = f":flag_{country.lower()}:"
            city += f", {country}"

        # https://openweathermap.org/weather-conditions
        conditions = {
            (200, 299): "🌩️",  # thunderstorm
            (300, 399): "🌧️",  # drizzle
            (500, 599): "🌧️",  # rain
            (600, 699): "❄️",  # snow
            (700, 799): "💨",  # atmosphere
            (800, 800): "☀️",  # clear
            (801, 809): "☁️",  # clouds
        }

        emoji = next(
            (e for c, e in conditions.items() if c[0] <= condition <= c[1]), ""
        )

        msg = (
            f"{flag} |  **Weather for {city}**\n"
            f"**Weather:** {emoji} ({description})\n"
            f"**Temp:** {temp} °C **Feels like:** {feels_like} °C\n"
            f"**Wind:** {wind} m/s **Humidity:** {humidity}% **Cloudiness:** {cloudiness}%"
        )

        await interaction.followup.send(msg)

        if interaction.response.is_done():  # noqa
            return

    @app_commands.command(name="time", description="Show the date and time of a city")
    @app_commands.describe(
        city="Enter the city for which you'd like to check the date and time."
    )
    async def time(self, interaction: discord.Interaction, *, city: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        try:
            data = await self.fetch_weather_data(city)
        except Exception as exc:
            await interaction.followup.send(exc)
            return
        now = datetime.now(timezone.utc)

        offset = data["timezone"]
        sunrise = data["sys"]["sunrise"]
        sunset = data["sys"]["sunset"]

        emoji = "🌞" if sunrise <= now.timestamp() < sunset else "🌝"
        timestamp = now + timedelta(seconds=offset)
        hours, minutes = divmod(offset / 60, 60)

        await interaction.followup.send(
            f"{emoji} **{timestamp:%d/%m/%Y %H:%M:%S}** (UTC {hours:+03.0f}:{minutes:02.0f})"
        )

        if interaction.response.is_done():  # noqa
            return

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))
