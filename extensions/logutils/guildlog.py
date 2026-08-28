import asyncio
import difflib
import itertools
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Tuple, Union, TYPE_CHECKING

import discord
from discord.ext import commands

from utils.text import to_discord_timestamp, clip
from utils.misc import log_to
from utils.containers import separator
from utils.deletions import bot_deleted
from extensions.management.moderator.views.buttons.user_info import UserInfoButton
from constants import Guilds, Channels, Emojis

if TYPE_CHECKING:
    from bot import DDNet

VALID_IMAGE_FORMATS = (".webp", ".jpeg", ".jpg", ".png", ".gif")

ATTACHMENT_CACHE_TTL = 60 * 60
ATTACHMENT_MAX_FILE = 8 * 1024 * 1024
ATTACHMENT_CACHE_BUDGET = 100 * 1024 * 1024


def author_channel_label(message: discord.Message) -> str:
    author = message.author
    if isinstance(message.channel, discord.Thread):
        parent = message.channel.parent.id
        return f"{author.name} → <#{parent}> → Thread: <#{message.channel.id}>"
    return f"{author.name} → <#{message.channel.id}>"


class DeletedMessageLog(discord.ui.LayoutView):
    def __init__(self, message: discord.Message, files: List[discord.File], missing: List[str]):
        super().__init__(timeout=None)
        author = message.author

        content = message.content.strip()
        body = discord.utils.escape_mentions(clip(content, 3000)) if content else "*No content*"

        items = [
            discord.ui.Section(
                f"### Message deleted\n"
                f"**{author_channel_label(message)}**\n"
                f"At: {to_discord_timestamp(discord.utils.utcnow(), 'f')}",
                accessory=discord.ui.Thumbnail(author.display_avatar.with_static_format("png").url),
            )
        ]

        items.append(discord.ui.TextDisplay(body))
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
        if not author.bot:
            items.append(discord.ui.ActionRow(UserInfoButton(author.id)))


        self.add_item(discord.ui.Container(*items, accent_colour=0xDD2E44))


class GuildLog(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self._attachment_cache: dict[int, tuple[float, list[tuple[str, bytes]]]] = {}
        self._attachment_cache_bytes = 0

    @staticmethod
    def channel_excluded(channel) -> bool:
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

    async def log_message(self, message: discord.Message) -> bool:
        """Write one deleted message entry. Returns whether anything was logged"""
        if (
                not message.guild
                or message.guild.id != Guilds.DDNET
                or message.is_system()
                or self.channel_excluded(message.channel)
        ):
            return False

        if bot_deleted(message.id):
            # an automod removed it and writes its own alert, one per sweep
            self.drop_cached(message.id)
            return False

        files = self.repost_files(message.id)
        retained = {f.filename for f in files}
        missing = [a.filename for a in message.attachments if a.filename not in retained]

        await log_to(
            self.bot,
            Channels.LOG_MESSAGES,
            view=DeletedMessageLog(message, files, missing),
            files=files,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        await self.log_message(message)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: List[discord.Message]):
        messages.sort(key=lambda m: m.created_at)
        for message in messages:
            # only pace ourselves for entries we actually wrote
            if await self.log_message(message):
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


async def setup(bot: "DDNet"):
    await bot.add_cog(GuildLog(bot))
