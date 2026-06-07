import random

import discord
from discord.ext import commands

from constants import Guilds
from utils.json_helpers import load_map, save_map

AUTO_RESPONSES_PATH = "data/config/auto_responses.json"


class AutoResponses(commands.Cog):
    """Replies to messages containing configured trigger words"""

    def __init__(self, bot):
        self.bot = bot
        self.responses: dict[str, str] = {}

    async def cog_load(self):
        self.responses = load_map(AUTO_RESPONSES_PATH)

    def _save(self) -> None:
        save_map(AUTO_RESPONSES_PATH, self.responses)

    async def add_response(self, trigger: str, response: str) -> tuple[bool, str]:
        """Add (duh) a trigger/response pair"""
        trigger = trigger.strip()
        response = response.strip()
        if not trigger:
            return False, "The trigger can't be empty."
        if trigger in self.responses:
            return False, f"`{trigger}` already has an auto-response."

        self.responses[trigger] = response
        self._save()
        return True, f"Added an auto-response for `{trigger}`."

    async def remove_response(self, trigger: str) -> tuple[bool, str]:
        """Remove (duh) a trigger by its exact text"""
        trigger = trigger.strip()
        if trigger not in self.responses:
            return False, f"No auto-response found with trigger `{trigger}`."

        del self.responses[trigger]
        self._save()
        return True, f"Removed the auto-response for `{trigger}`."

    def pairs(self) -> list[tuple[str, str]]:
        """(trigger, response) pairs for the admin hub list view."""
        return list(self.responses.items())

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or message.guild.id != Guilds.DDNET:
            return

        content = message.content.lower()
        for triggers, response in self.responses.items():
            trigger_list = triggers.lower().split(", ")
            if any(word in content for word in trigger_list):
                await message.reply(random.choice(response.split(", ")))
                break


async def setup(bot):
    await bot.add_cog(AutoResponses(bot))
