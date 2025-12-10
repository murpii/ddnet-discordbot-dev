import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union
import discord

from constants import Guilds


class ModAction(enum.Enum):
    BAN = enum.auto()
    UNBAN = enum.auto()
    KICK = enum.auto()
    TIMEOUT = enum.auto()
    UNTIMEOUT = enum.auto()


@dataclass
class PendingAction:
    moderator: discord.abc.User
    action: ModAction
    reason: Optional[str] = None


# TODO: Just use len() of the rows fetched from the db for each type
@dataclass
class MemberInfo:
    """
    Stores moderation-related information for a Discord user or member.
    Tracks timeouts, bans, kicks, nickname changes, and testing bans for moderation purposes.

    Attributes:
        member: The Discord user or member.
        timed_out: The datetime when the member was timed out, if applicable.
        timeouts: The total number of timeouts for the member.
        timeout_reasons: List of tuples containing timeout reasons and timestamps.
        banned: Whether the member is currently banned.
        bans: The total number of bans for the member.
        ban_reasons: List of tuples containing ban reasons and timestamps.
        kicks: The total number of kicks for the member.
        kick_reasons: List of tuples containing kick reasons and timestamps.
        banned_from_testing: Whether the member is banned from testing.
        invoked_by: The name of the user who invoked the last action.
        nicknames: List of tuples containing nickname changes and timestamps.
    """

    member: Union[discord.User, discord.Member]
    timed_out: Optional[datetime] = None
    timeouts: int = 0
    timeout_reasons: List[tuple] = field(default_factory=list)
    banned: bool = False
    bans: int = 0
    ban_reasons: List[tuple] = field(default_factory=list)
    kicks: int = 0
    kick_reasons: List[tuple] = field(default_factory=list)
    banned_from_testing: bool = False
    invoked_by: str = "Unknown"
    nicknames: List[tuple] = field(default_factory=list)

    def __repr__(self):
        return (
            f"MemberInfo: Member name: ({self.member}, id: {self.member.id}), "
            f"Timeouts: {self.timeouts}, Total Bans: {self.bans}, Total Kicks: {self.kicks}, "
            f"Timeout Reasons: {self.timeout_reasons}, Ban Reasons: {self.ban_reasons}, Kick Reason {self.kick_reasons} "
            f"Nicknames {self.nicknames}"
        )


class ModeratorDB:
    def __init__(self, bot):
        self.bot = bot
        self.actions: dict[int, PendingAction] = {}

    async def fetch_user_info(self, member: Union[discord.User, discord.Member]) -> Optional[MemberInfo]:
        guild = self.bot.get_guild(Guilds.DDNET)
        member = await self.bot.get_or_fetch_member(guild=guild, user_id=member.id)

        query = """
                SELECT type,
                       reason,
                       timestamp,
                       invoked_by
                FROM discordbot_user_info
                WHERE user_id = %s
                """
        results = await self.bot.fetch(query, member.id, fetchall=True)

        timeout_reasons = []
        ban_reasons = []
        kick_reasons = []
        nicknames = []
        timeouts = bans = kicks = 0
        action_invoked_by = "Unknown"
        timeout = None

        for row in results:
            action_type = row[0]
            action_reason = row[1]
            action_timestamp = row[2]
            action_invoked_by = row[3]

            if action_type == 'timeout':
                timeouts += 1
                timeout_reasons.append((action_reason, action_timestamp))
            elif action_type == 'ban':
                bans += 1
                ban_reasons.append((action_reason, action_timestamp))
            elif action_type == 'kick':
                kicks += 1
                kick_reasons.append((action_reason, action_timestamp))
            elif action_type == "nickname":
                nicknames.append((action_reason, action_timestamp))

        guild = self.bot.get_guild(Guilds.DDNET)
        banlist = [entry async for entry in guild.bans()]
        currently_banned = any((entry.user.id == member.id for entry in banlist))

        if isinstance(member, discord.Member) and member.timed_out_until:  # noqa
            timeout = member.timed_out_until  # noqa

        query = """
                SELECT TRUE
                FROM discordbot_testing_bans
                WHERE banned_user_id = %s
                  AND banned_bool
                """
        row = await self.bot.fetch(query, member.id)
        currently_banned_from_testing = bool(row)

        return MemberInfo(
            member=member,
            timed_out=timeout, timeouts=timeouts,
            timeout_reasons=timeout_reasons,
            banned=currently_banned, bans=bans, ban_reasons=ban_reasons,
            kicks=kicks, kick_reasons=kick_reasons,
            banned_from_testing=currently_banned_from_testing,
            invoked_by=action_invoked_by,
            nicknames=nicknames,
        )

    async def remove_user_entry(
            self,
            member: Union[discord.User, discord.Member],
            entry_type: str,  # 'timeout', 'ban', 'kick'
            *,
            reason: Optional[str] = None,
            timestamp: Optional[datetime] = None,
    ) -> int:
        """
        Remove user moderation entry/entries from the database.
        Returns the number of rows deleted.
        """

        conditions = ["type = %s", "user_id = %s"]
        params = [entry_type, member.id]

        if reason is not None:
            conditions.append("reason = %s")
            params.append(reason)

        if timestamp is not None:
            conditions.append("timestamp = %s")
            params.append(str(timestamp))

        where_clause = " AND ".join(conditions)
        query = f"DELETE FROM discordbot_user_info WHERE {where_clause}"
        return await self.bot.upsert(query, *params)

    async def log_action(
            self,
            invoker: discord.abc.User,
            user: discord.abc.User,
            action: ModAction,
            reason: str
    ):
        user_info = await self.fetch_user_info(user) or MemberInfo(member=user)

        query = """
                INSERT INTO discordbot_user_info (user_id, type, reason, invoked_by)
                VALUES (%s, %s, %s, %s)
                """

        await self.bot.upsert(query, user.id, action.name.lower(), reason, invoker.name)

        if action == ModAction.BAN:
            user_info.bans += 1
        elif action == ModAction.KICK:
            user_info.kicks += 1
        elif action == ModAction.TIMEOUT:
            user_info.timeouts += 1

    async def log_nickname_change(
            self,
            user: discord.abc.User,
            old: str,
            new: str,
            *,
            invoked_by: discord.abc.User,
    ):
        reason = f"{old} -> {new}"

        query = """
                INSERT INTO discordbot_user_info (user_id,
                                                  type,
                                                  reason,
                                                  invoked_by)
                VALUES (%s, %s, %s, %s)
                """
        await self.bot.upsert(
            query,
            user.id,
            "nickname",
            reason,
            invoked_by.name,
        )

    async def import_existing_bans(self, guild: discord.Guild) -> str:
        bans = [entry async for entry in guild.bans()]
        if not bans:
            raise ValueError("No bans found.")

        query_existing = """
                         SELECT user_id
                         FROM discordbot_user_info
                         WHERE type = 'ban' \
                         """
        rows = await self.bot.fetch(query_existing, fetchall=True)
        already_banned = {row[0] for row in rows}

        insert_query = """
                       INSERT INTO discordbot_user_info
                           (user_id, type, reason, invoked_by)
                       VALUES (%s, 'ban', %s, 'IMPORTED BAN') \
                       """

        count = 0
        for entry in bans:
            user = entry.user
            if user.id in already_banned:
                continue

            reason = entry.reason or "No reason provided"
            await self.bot.upsert(insert_query, user.id, reason)
            count += 1

        return f"Imported {count} new bans into the database."
