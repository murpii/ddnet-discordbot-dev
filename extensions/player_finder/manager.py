from dataclasses import dataclass
from datetime import datetime
from typing import Union

import discord


@dataclass(slots=True, kw_only=True)
class Player:
    name: str
    reason: str
    expiry_date: datetime
    added_by: discord.User

    def __repr__(self):
        return (
            f"Player(name={self.name}, "
            f"reason={self.reason}, "
            f"expiry_date={self.expiry_date}, "
            f"added_by={self.added_by})"
        )


class PlayerfinderManager:
    def __init__(self, bot):
        self.bot = bot
        self.players = []

    async def load_players(self):
        query = """
        SELECT 
            name, 
            expiry_date, 
            added_by, 
            reason 
        FROM 
            discordbot_playerfinder
        """
        rows = await self.bot.fetch(query, fetchall=True)

        for row in rows:
            name, expiry_date, added_by, reason = row
            player = Player(
                name=name, expiry_date=expiry_date, added_by=added_by, reason=reason
            )
            self.players.append(player)

    async def insert(self, player: Player):
        query = """
        INSERT INTO 
            discordbot_playerfinder (
                name, 
                expiry_date, 
                added_by, 
                reason
            )
        VALUES 
            (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            expiry_date = VALUES(expiry_date),
            added_by = VALUES(added_by),
            reason = VALUES(reason)
        """
        await self.bot.upsert(
            query, player.name, player.expiry_date, str(player.added_by), player.reason
        )

    async def delete(self, player: Player):
        query = """
        DELETE FROM 
            discordbot_playerfinder
        WHERE 
            name = %s
        """
        await self.bot.upsert(query, player.name)

    async def update(self, player: Player):
        query = """
        UPDATE 
            discordbot_playerfinder
        SET 
            expiry_date = %s, 
            added_by = %s, 
            reason = %s
        WHERE 
            name = %s
        """
        await self.bot.upsert(
            query, player.expiry_date, str(player.added_by), player.reason, player.name
        )

    async def add_player(
            self,
            name: str,
            expiry_date: datetime,
            added_by: Union[discord.User, discord.Member],
            reason: str
    ) -> Player:
        player = Player(name=name, expiry_date=expiry_date,added_by=added_by, reason=reason)
        await self.insert(player)
        self.players.append(player)
        return player

    async def del_player(self, player: Player):
        await self.delete(player)
        self.players.remove(player)

    def find_player(self, name) -> Player:
        return next((player for player in self.players if player.name == name), None)

    async def edit_reason(self, name, reason=None) -> tuple[str, Player]:
        player = self.find_player(name)
        old_reason = player.reason
        if player is None:
            raise ValueError(f"No player found with name {name}")
        if reason is not None:
            player.reason = reason
            await self.update(player)
        return old_reason, player
