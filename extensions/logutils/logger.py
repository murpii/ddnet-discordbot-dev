import asyncio
import logging
import os
import time
import difflib
import traceback
import discord
from discord.ext import commands
import itertools
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Tuple, Union

from utils.text import escape, to_discord_timestamp, clip
from utils.misc import log_to
from utils.containers import separator
from constants import Guilds, Channels, Emojis

VALID_IMAGE_FORMATS = (".webp", ".jpeg", ".jpg", ".png", ".gif")

ATTACHMENT_CACHE_TTL = 60 * 60  # keep cached bytes for 1 hour
ATTACHMENT_MAX_FILE = 8 * 1024 * 1024  # only cache attachments up to 8 MiB
ATTACHMENT_CACHE_BUDGET = 100 * 1024 * 1024  # total cached bytes kept at once

if not os.path.exists("logs"):
    os.mkdir("logs")


def setup_logger(name, level, filename, propagate):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(filename, "a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# ---------------------------------------------------------------------------
# Rate limit logging
#
# discord.py never raises an error when Discord rate limits us but instead it quietly
# sleeps and retries, and the only trace is a log record on its "discord.http"
# or "discord.gateway" logger. The watcher below picks those records out and
# re-logs them to logs/ratelimits.log together with the code path that made
# the request, so we can see *what* the bot was doing when it got slowed down.
# ---------------------------------------------------------------------------

# repo root, two folders up from extensions/logutils/logger.py.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RATELIMIT_MESSAGE_PREFIXES = (
    "We are being rate limited.",  # a request got an actual 429 response
    "Global rate limit has been hit.",  # the bot tripped the global limit
    "A rate limit bucket",  # bucket drained; discord.py waits before sending
    "WebSocket in shard ID",  # gateway (websocket) send limiter kicked in
)


def is_ratelimit_record(record: logging.LogRecord) -> bool:
    template = str(record.msg)
    return template.startswith(RATELIMIT_MESSAGE_PREFIXES) or "429" in template


REAL_THROTTLE_PREFIXES = (
    "We are being rate limited.",  # an actual 429 response
    "Global rate limit has been hit.",  # the global limit was hit
)


def is_real_throttle(record: logging.LogRecord) -> bool:
    template = str(record.msg)
    return template.startswith(REAL_THROTTLE_PREFIXES) or "429" in template


def describe_caller() -> str:
    """Describe what the bot is doing right now: the current asyncio task
    plus the stack frames that belong to our own code.

    This works because discord.py logs rate limits from inside the very
    coroutine that performs the HTTP request. At that moment the call
    still contains the frames of our code that triggered it, for example
    overseer.py sync_messages -> discord Message.edit -> http request.
    """
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    lines = [f"task: {task.get_name() if task else 'unknown'}"]

    this_file = os.path.abspath(__file__)
    for frame in traceback.extract_stack():
        filename = os.path.abspath(frame.filename)
        if not filename.startswith(PROJECT_ROOT):
            continue
        if "site-packages" in filename:
            continue  # discord.py and other libraries (the venv lives inside the repo)
        if filename == this_file:
            continue  # the watcher itself
        relative = os.path.relpath(filename, PROJECT_ROOT)
        lines.append(f"{relative}:{frame.lineno} in {frame.name}")

    return "\n    ".join(lines)


class RatelimitWatcher(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.ratelimit_log = logging.getLogger("ratelimits")

    def filter(self, record: logging.LogRecord) -> bool:
        return is_ratelimit_record(record)

    @staticmethod
    def _is_console_handler(handler: logging.Handler) -> bool:
        return isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)

    def emit(self, record: logging.LogRecord) -> None:
        real = is_real_throttle(record)
        enriched = logging.LogRecord(
            name="ratelimits",
            level=logging.WARNING if real else logging.INFO,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=f"{record.getMessage()}\n    {describe_caller()}",
            args=None,
            exc_info=None,
        )
        for handler in self.ratelimit_log.handlers:
            if not real and self._is_console_handler(handler):
                continue
            if enriched.levelno >= handler.level:
                handler.handle(enriched)


class HttpLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or is_ratelimit_record(record)


class DropRatelimitRecords(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name.startswith("discord.") and is_ratelimit_record(record))


def setup_ratelimit_logging():
    http_log = logging.getLogger("discord.http")
    if any(isinstance(h, RatelimitWatcher) for h in http_log.handlers):
        return

    setup_logger("ratelimits", logging.INFO, "logs/ratelimits.log", propagate=False)

    watcher = RatelimitWatcher()

    http_log.setLevel(logging.DEBUG)
    http_log.addFilter(HttpLogFilter())
    http_log.addHandler(watcher)

    logging.getLogger("discord.gateway").addHandler(watcher)
    drop = DropRatelimitRecords()
    for handler in logging.getLogger().handlers:
        handler.addFilter(drop)


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # root logger (file + console; replaces the old logging.basicConfig call)
    setup_logger(None, logging.INFO, "logs/bot.log", propagate=True)
    # tickets logger
    setup_logger("tickets", logging.INFO, "logs/tickets.log", propagate=False)
    # skin submits logger
    setup_logger("skin_submits", logging.INFO, "logs/skin_submits.log", propagate=False)
    # rename logger
    setup_logger("renames", logging.INFO, "logs/renames.log", propagate=False)

    # root
    logging.getLogger("discord").setLevel(logging.WARNING)

    # rate limit visibility -- logs/ratelimits.log. Also configures the
    # "discord.http" logger (DEBUG + filter), replacing the old plain
    # WARNING level it had before.
    setup_ratelimit_logging()

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, app_command):
        if interaction.guild is None:
            destination = "Private Message"
        else:
            destination = f"#{interaction.channel} ({interaction.guild})"

        options = interaction.data.get("options", [])
        if args := {opt["name"]: opt.get("value") for opt in options}:  # noqa
            logging.info("%s used /%s %s in %s", interaction.user, app_command.name, args, destination)
        else:
            logging.info("%s used /%s in %s", interaction.user, app_command.name, destination)


def author_channel_label(message: discord.Message) -> str:
    author = message.author
    if isinstance(message.channel, discord.Thread):
        parent = message.channel.parent.name
        return f"{author} → #{parent} → Thread: #{message.channel}"
    return f"{author} → #{message.channel}"


class DeletedMessageLog(discord.ui.LayoutView):
    def __init__(self, message: discord.Message, files: List[discord.File], missing: List[str]):
        super().__init__(timeout=None)
        author = message.author

        content = message.content.strip()
        body = discord.utils.escape_mentions(clip(content, 3000)) if content else "*No content*"

        items = [
            discord.ui.Section(
                f"### Message deleted\n"
                f"**{discord.utils.escape_mentions(author_channel_label(message))}**\n\n"
                f"{body}",
                accessory=discord.ui.Thumbnail(author.display_avatar.with_static_format("png").url),
            )
        ]

        # every retained image, not just the first one.
        if files:
            items.append(
                discord.ui.MediaGallery(
                    *(discord.MediaGalleryItem(f"attachment://{f.filename}") for f in files)
                )
            )

        # attachments we could not keep
        if missing:
            items.append(
                discord.ui.TextDisplay(
                    "**Attachments (not retained):**\n"
                    + discord.utils.escape_mentions(clip("\n".join(missing), 1000))
                )
            )

        items.append(separator())
        items.append(
            discord.ui.TextDisplay(
                f"-# Author ID: {author.id} | Message ID: {message.id} "
                f"| {to_discord_timestamp(discord.utils.utcnow(), 'f')}"
            )
        )

        self.add_item(discord.ui.Container(*items, accent_colour=0xDD2E44))


class GuildLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._attachment_cache: dict[int, tuple[float, list[tuple[str, bytes]]]] = {}
        self._attachment_cache_bytes = 0

    @staticmethod
    def channel_excluded(channel) -> bool:
        """Channels we never log/cache. Threads inside the LOGS channel (the log
        sub-threads) are excluded too, so the bot never logs its own logs."""
        category = getattr(channel, "category", None)
        return (
                channel.id in (Channels.LOGS, Channels.PLAYERFINDER)
                or getattr(channel, "parent_id", None) == Channels.LOGS
                or (category is not None and category.id == Channels.CAT_INTERNAL)
                or channel.name.startswith(("complaint-", "admin-mail-", "rename-"))
        )

    def drop_cached(self, message_id: int) -> list[tuple[str, bytes]]:
        entry = self._attachment_cache.pop(message_id, None)
        if entry is None:
            return []
        self._attachment_cache_bytes -= sum(len(data) for _, data in entry[1])
        return entry[1]

    def purge_expired_attachments(self) -> None:
        now = time.monotonic()
        for mid in [mid for mid, (expiry, _) in self._attachment_cache.items() if expiry <= now]:
            self.drop_cached(mid)

    def evict_attachments_until(self, budget: int) -> None:
        for mid in list(self._attachment_cache):
            if self._attachment_cache_bytes <= budget:
                break
            self.drop_cached(mid)

    async def attachment_cache(self, message: discord.Message) -> None:
        items: list[tuple[str, bytes]] = []
        for attachment in message.attachments:
            if not attachment.filename.lower().endswith(VALID_IMAGE_FORMATS):
                continue
            if attachment.size > ATTACHMENT_MAX_FILE:
                continue
            try:
                items.append((attachment.filename, await attachment.read()))
            except discord.HTTPException:
                continue

        if not items:
            return

        self.purge_expired_attachments()
        total = sum(len(data) for _, data in items)
        self.evict_attachments_until(ATTACHMENT_CACHE_BUDGET - total)
        self._attachment_cache[message.id] = (time.monotonic() + ATTACHMENT_CACHE_TTL, items)
        self._attachment_cache_bytes += total

    def repost_files(self, message_id: int) -> list[discord.File]:
        files: list[discord.File] = []
        seen: set[str] = set()
        for name, data in self.drop_cached(message_id):
            unique, counter = name, 1
            while unique in seen:
                base, dot, ext = name.rpartition(".")
                unique = f"{base}_{counter}.{ext}" if dot else f"{name}_{counter}"
                counter += 1
            seen.add(unique)
            files.append(discord.File(BytesIO(data), filename=unique))
        return files

    @commands.Cog.listener("on_message")
    async def cache_attachments(self, message: discord.Message) -> None:
        if (
                not message.guild
                or message.guild.id != Guilds.DDNET
                or not message.attachments
                or self.channel_excluded(message.channel)
        ):
            return
        await self.attachment_cache(message)

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
                or self.channel_excluded(message.channel)
        ):
            return

        files = self.repost_files(message.id)
        retained = {f.filename for f in files}
        missing = [a.filename for a in message.attachments if a.filename not in retained]

        await log_to(
            self.bot,
            Channels.LOG_MESSAGES,
            view=DeletedMessageLog(message, files, missing),
            files=files,
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        await self.log_message(message)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: List[discord.Message]):
        # sort by timestamp to make sure messages are logged in correct order
        messages.sort(key=lambda m: m.created_at)
        for message in messages:
            await self.log_message(message)
            await asyncio.sleep(1)

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
                or before.author.bot
                or self.channel_excluded(before.channel)
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
        embed.set_author(
            name=author_channel_label(before),
            icon_url=author.display_avatar.with_static_format("png"),
        )
        embed.set_footer(text=f"Author ID: {author.id} | Message ID: {before.id}")

        await log_to(self.bot, Channels.LOG_MESSAGES, embed=embed)

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
