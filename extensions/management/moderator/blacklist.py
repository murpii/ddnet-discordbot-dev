import contextlib
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from constants import Channels, Guilds
from extensions.management.moderator.views.containers.blacklist import (
    BlacklistAlertView,
)
from utils.checks import is_staff
from utils.deletions import delete_messages
from utils.json_helpers import load_map, save_map
from utils.misc import log_to

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

DEFAULT_RESPONSE = "Your message contained a blacklisted word and has been removed."
BLACKLIST_PATH = "data/config/blacklist.json"


class Blacklist(commands.Cog):
    """Deletes messages containing blacklisted words.

      - The wordlist lives in data/config/blacklist.json (a {trigger: response} map),
        is cached in memory and compiled
      - Edited messages are checked too, so a word can't be edited in later
      - Hits are logged to the logs channel

    Staff, ticket channels and other guilds are exempt.
    """

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.words: dict[str, str] = {}  # lowercased trigger -> response
        self.pattern: Optional[re.Pattern] = None
        self.setup = False

    async def cog_load(self):
        await self.load_words()

    async def load_words(self):
        self.words = {
            trigger.lower(): response
            for trigger, response in load_map(BLACKLIST_PATH).items()
        }
        self.rebuild_pattern()
        self.setup = True
        log.info("Blacklist: loaded %d words", len(self.words))

    def rebuild_pattern(self):
        if not self.words:
            self.pattern = None
            return

        escaped = sorted((re.escape(word) for word in self.words), key=len, reverse=True)
        self.pattern = re.compile("|".join(escaped), re.IGNORECASE)

    def is_exempt(self, message: discord.Message) -> bool:
        return (
                message.author.bot
                or message.guild is None
                or message.guild.id != Guilds.DDNET
                or message.channel.id in self.bot.ticket_manager.tickets
                or is_staff(message.author, roles="mods")
        )

    async def enforce(self, message: discord.Message):
        if not self.setup:
            await self.load_words()
        if self.pattern is None or self.is_exempt(message):
            return

        match = self.pattern.search(message.content)
        if match is None:
            return

        trigger = match[0].lower()
        response = self.words.get(trigger, DEFAULT_RESPONSE)

        if not await delete_messages([message], reason=f"Blacklisted word: {trigger}"):
            return  # already gone, or we can't moderate here

        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await message.author.send(response)
        await log_to(
            self.bot, Channels.LOG_MOD_ALERTS,
            view=BlacklistAlertView(message.author, message.channel, trigger, message.content),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener("on_message")
    async def check_message(self, message: discord.Message):
        await self.enforce(message)

    @commands.Cog.listener("on_message_edit")
    async def check_edited_message(self, before: discord.Message, after: discord.Message):
        if before.content != after.content:
            await self.enforce(after)

    async def add_word(self, trigger: str, response: str = None) -> tuple[bool, str]:
        """Add a word (duh)"""
        trigger_key = trigger.lower().strip()
        if not trigger_key:
            return False, "The trigger can't be empty."
        if trigger_key in self.words:
            return False, f"`{trigger_key}` is already blacklisted."

        response = response or DEFAULT_RESPONSE
        self.words[trigger_key] = response
        save_map(BLACKLIST_PATH, self.words)
        self.rebuild_pattern()
        return True, f"Added `{trigger_key}` to the blacklist.\nResponse: {response}"

    async def remove_word(self, trigger: str) -> tuple[bool, str]:
        """Remove (duh) a word"""
        trigger_key = trigger.lower().strip()
        if trigger_key not in self.words:
            return False, f"`{trigger_key}` is not on the blacklist."

        del self.words[trigger_key]
        save_map(BLACKLIST_PATH, self.words)
        self.rebuild_pattern()
        return True, f"Removed `{trigger_key}` from the blacklist."
