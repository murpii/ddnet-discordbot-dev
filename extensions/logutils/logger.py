import contextlib
import logging
import os
import difflib
import asyncmy
import discord
from discord.ext import commands
import itertools
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Tuple, Union

from utils.text import escape
from constants import Guilds, Channels, Emojis

VALID_IMAGE_FORMATS = (".webp", ".jpeg", ".jpg", ".png", ".gif")

if not os.path.exists("logs"):
    os.mkdir("logs")


def setup_logger(name, level, filename, propagate):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    file_handler = logging.FileHandler(filename, "a", encoding="utf-8")
    formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if name is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

    # root logger
    setup_logger(None, logging.INFO, "logs/bot.log", propagate=True)
    # map testing logger
    setup_logger("mt", logging.INFO, "logs/map_testing.log", propagate=False)
    # tickets logger
    setup_logger("tickets", logging.INFO, "logs/tickets.log", propagate=False)
    # skin submits logger
    setup_logger("skin_submits", logging.INFO, "logs/skin_submits.log", propagate=False)
    # rename logger
    setup_logger("renames", logging.INFO, "logs/renames.log", propagate=False)

    # root
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, app_command):
        if interaction.guild is None:
            destination = "Private Message"
            guild_id = None
        else:
            destination = f"#{interaction.channel} ({interaction.guild})"
            guild_id = interaction.guild.id

        options = interaction.data.get("options", [])
        if args := {opt["name"]: opt.get("value") for opt in options}:  # noqa
            logging.info("%s used /%s %s in %s", interaction.user, app_command.name, args, destination)
        else:
            logging.info("%s used /%s in %s", interaction.user, app_command.name, destination)

        query = """
        INSERT INTO discordbot_stats_commands (guild_id, channel_id, author_id, timestamp, command) 
        VALUES (%s, %s, %s, %s, %s);
        """

        values = (
            guild_id,
            interaction.channel.id,
            interaction.user.id,
            interaction.created_at.replace(tzinfo=None),
            interaction.command.qualified_name,
        )

        with contextlib.suppress(asyncmy.Connection.DataError):
            await self.bot.upsert(query, *values)


class GuildLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != Guilds.DDNET or member.bot:
            return

        msg = (
            f"📥 {member.mention}, Welcome to **DDraceNetwork's Discord**! "
            f"Please make sure to read <#{Channels.WELCOME}>. "
            f"Have a great time here <:happy:{Emojis.HAPPY}>"
        )
        chan = self.bot.get_channel(Channels.JOIN_LEAVE)
        await chan.send(msg)

    @commands.Cog.listener()
    async def on_member_remove(self, user: Union[discord.User, discord.Member]):
        if user.guild.id != Guilds.DDNET or user.bot:
            return

        msg = f"📤 {user.mention} just left the server <:mmm:{Emojis.MMM}>"
        chan = self.bot.get_channel(Channels.JOIN_LEAVE)
        await chan.send(msg)

    async def log_message(self, message: discord.Message):
        if (
            not message.guild
            or message.guild.id != Guilds.DDNET
            or message.is_system()
            or message.channel.id in (Channels.LOGS, Channels.PLAYERFINDER)
            or message.channel.category.id == Channels.CAT_INTERNAL
            or message.channel.name.startswith(("complaint-", "admin-mail-", "rename-"))
        ):
            return

        embed = discord.Embed(
            title="Message deleted",
            description=message.content,
            color=0xDD2E44,
            timestamp=datetime.now(timezone.utc),
        )

        file = None
        if message.attachments:
            attachment = message.attachments[0]

            # can only properly recover images
            if attachment.filename.endswith(VALID_IMAGE_FORMATS):
                buf = BytesIO()
                try:
                    await attachment.save(buf, use_cached=True)
                except discord.HTTPException:
                    pass
                else:
                    file = discord.File(buf, filename=attachment.filename)
                    embed.set_image(url=f"attachment://{attachment.filename}")

        author = message.author
        if isinstance(message.channel, discord.Thread):
            parent = message.channel.parent.name
            author_name_and_channel = (
                f"{author} → #{parent} → Thread: #{message.channel}"
            )
        else:
            author_name_and_channel = f"{author} → #{message.channel}"

        embed.set_author(
            name=author_name_and_channel,
            icon_url=author.display_avatar.with_static_format("png"),
        )
        embed.set_footer(text=f"Author ID: {author.id} | Message ID: {message.id}")

        chan = self.bot.get_channel(Channels.LOGS)
        await chan.send(file=file, embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        await self.log_message(message)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: List[discord.Message]):
        # sort by timestamp to make sure messages are logged in correct order
        messages.sort(key=lambda m: m.created_at)
        for message in messages:
            await self.log_message(message)

    @staticmethod
    def format_content_diff(before: str, after: str) -> Tuple[str, str]:
        """
        Formats the content difference between two strings.

        Args:
            before (str): The original string.
            after (str): The modified string.

        Returns:
            Tuple[str, str]: The formatted differences, one for the removed content and one for the added content.
        """
        # taken from https://github.com/python-discord/bot/pull/646
        diff = difflib.ndiff(before.split(), after.split())
        groups = [
            (c, [s[2:] for s in w])
            for c, w in itertools.groupby(diff, key=lambda d: d[0])
            if c != "?"
        ]

        out = {"-": [], "+": []}
        for i, (code, words) in enumerate(groups):
            sub = " ".join(words)
            if code in "-+":
                out[code].append(f"[{sub}](http://{code})")
            else:
                if len(words) > 2:
                    sub = ""
                    if i > 0:
                        sub += words[0]

                    sub += " ... "

                    if i < len(groups) - 1:
                        sub += words[-1]

                out["-"].append(sub)
                out["+"].append(sub)

        return " ".join(out["-"]), " ".join(out["+"])

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if (
            not before.guild
            or before.guild.id != Guilds.DDNET
            or before.is_system()
            or before.channel.id == Channels.LOGS
            or before.channel.category.id == Channels.CAT_INTERNAL
            or before.author.bot
            or before.channel.name.startswith(("complaint-", "admin-mail-", "rename-"))
        ):
            return

        if before.content == after.content:
            return

        desc = f"[Jump to message]({before.jump_url})"
        embed = discord.Embed(
            title="Message edited",
            description=desc,
            color=0xF5B942,
            timestamp=datetime.now(timezone.utc),
        )

        before_content, after_content = self.format_content_diff(
            before.content, after.content
        )
        embed.add_field(name="Before", value=before_content or "\u200b", inline=False)
        embed.add_field(name="After", value=after_content or "\u200b", inline=False)

        author = before.author
        if isinstance(before.channel, discord.Thread):
            parent = before.channel.parent.name
            author_name_and_channel = (
                f"{author} → #{parent} → Thread: #{before.channel}"
            )
        else:
            author_name_and_channel = f"{author} → #{before.channel}"

        embed.set_author(
            name=author_name_and_channel,
            icon_url=author.display_avatar.with_static_format("png"),
        )
        embed.set_footer(text=f"Author ID: {author.id} | Message ID: {before.id}")

        chan = self.bot.get_channel(Channels.LOGS)
        await chan.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def auto_publish(self, message: discord.Message):
        if message.channel.id in (Channels.ANNOUNCEMENTS, Channels.MAP_RELEASES):
            if message.reference:  # Can't publish message replies
                return
            else:
                await message.publish()


async def setup(bot):
    await bot.add_cog(Logging(bot))
    await bot.add_cog(GuildLog(bot))
