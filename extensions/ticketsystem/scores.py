import asyncio
import json
import logging

from discord.ext import commands, tasks
from constants import Channels

log = logging.getLogger("tickets")
scores_lock = asyncio.Lock()


async def load_scores() -> dict:
    def read() -> dict:
        try:
            with open("data/ticket-system/scores.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    return await asyncio.to_thread(read)


async def increment_score(user_id: int) -> None:
    """Add one to a user's claim score"""
    async with scores_lock:
        scores = await load_scores()
        scores[str(user_id)] = scores.get(str(user_id), 0) + 1

        def _write() -> None:
            with open("data/ticket-system/scores.json", "w", encoding="utf-8") as f:
                json.dump(scores, f)

        await asyncio.to_thread(_write)


class TicketScores(commands.Cog):
    """Owns the hourly task that rebuilds the moderator channel score leaderboard"""

    def __init__(self, bot):
        self.bot = bot
        self.update_scores_topic.start()

    def cog_unload(self):
        self.update_scores_topic.cancel()

    @tasks.loop(hours=1)
    async def update_scores_topic(self):
        """|asyncio.task|
        Updates the topic of the moderator channel with the top scores.
        """
        scores = await load_scores()
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        topic = "Tickets Claimed:"
        for user_id, score in sorted_scores[:30]:
            entry = f" <@{user_id}> = {score} |"
            # channel topics cap out at 1024 chars
            if len(topic) + len(entry) > 1024:
                break
            topic += entry

        topic = topic.rstrip("|")

        channel = self.bot.get_channel(Channels.MODERATOR)
        if channel and (channel.topic or "") != topic:
            await channel.edit(topic=topic)

    @update_scores_topic.before_loop
    async def before_update_scores_topic(self):
        await self.bot.wait_until_ready()
