import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Union, Optional, Any, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot import DDNet


@dataclass(slots=True, kw_only=True)
class Player:
    """
    Represents a player with ban information and metadata.
    This class stores details about a player, including their name, ban reason, expiry date, who added them, and an optional ban link.
    """
    name: str
    reason: str
    expiry_date: datetime
    added_by: discord.abc.User | str
    ban_link: Optional[str] = None

    def __repr__(self):
        return json.dumps(
            {
                "name": self.name,
                "reason": self.reason,
                "expiry_date": str(self.expiry_date),
                "added_by": str(self.added_by),
                "ban_link": self.ban_link,
            },
            indent=4
        )


class PlayerfinderManager:
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.players = []

    async def load_players(self):
        query = """
                SELECT name,
                       expiry_date,
                       added_by,
                       reason,
                       link
                FROM discordbot_playerfinder \
                """
        rows = await self.bot.fetch(query, fetchall=True)

        # rebuild from scratch so calling this twice can't duplicate entries
        self.players.clear()
        for row in rows:
            name, expiry_date, added_by, reason, link = row
            player = Player(
                name=name, expiry_date=expiry_date, added_by=added_by, reason=reason, ban_link=link
            )
            self.players.append(player)

    async def add(self, player: Player):
        query = """
                INSERT INTO discordbot_playerfinder (name,
                                                     expiry_date,
                                                     added_by,
                                                     reason,
                                                     link)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE expiry_date = VALUES(expiry_date),
                                        added_by    = VALUES(added_by),
                                        reason      = VALUES(reason),
                                        link        = VALUES(link) \
                """

        await self.bot.upsert(
            query, player.name, player.expiry_date, str(player.added_by), player.reason, player.ban_link
        )

        existing = self.find_player(player.name)
        if existing is not None:
            existing.expiry_date = player.expiry_date
            existing.added_by = player.added_by
            existing.reason = player.reason
            existing.ban_link = player.ban_link
            return existing

        self.players.append(player)
        return player

    async def delete(self, player: Player):
        query = """
                DELETE
                FROM discordbot_playerfinder
                WHERE name = %s \
                """
        await self.bot.upsert(query, player.name)
        self.players.remove(player)

    async def update(self, player: Player):
        # Updates (duh) the `player` in the database
        query = """
                UPDATE
                    discordbot_playerfinder
                SET expiry_date = %s,
                    added_by    = %s,
                    reason      = %s,
                    link        = %s
                WHERE name = %s
                """

        await self.bot.upsert(
            query,
            player.expiry_date,
            str(player.added_by),
            player.reason,
            player.ban_link,
            player.name
        )

    async def add_player(
            self,
            name: str,
            expiry_date: datetime,
            added_by: discord.abc.User | str,
            reason: str,
            link: str = None
    ) -> Player | None | Any:
        player = Player(name=name, expiry_date=expiry_date, added_by=added_by, reason=reason, ban_link=link)
        return await self.add(player)

    async def del_player(self, player: Player | str):
        if isinstance(player, str):
            original_name = player
            if found_player := self.find_player(player):
                player = found_player
            else:
                raise ValueError(f"No player found with name '{original_name}'")
        await self.delete(player)

    def find_player(self, name) -> Any | None:
        return next((player for player in self.players if player.name == name), None)

    async def edit_reason(self, name, reason) -> tuple[Any, Any | None]:
        player = self.find_player(name)
        if player is None:
            raise ValueError(f"No player found with name {name}")

        old_reason = player.reason
        player.reason = reason
        await self.update(player)
        return old_reason, player
