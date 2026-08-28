import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union, TYPE_CHECKING
import discord

from constants import Guilds

if TYPE_CHECKING:
    from bot import DDNet


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
        timeout_reasons: List of (entry_id, reason, timestamp, invoked_by) tuples, newest first.
        banned: Whether the member is currently banned.
        bans: The total number of bans for the member.
        ban_reasons: List of (entry_id, reason, timestamp, invoked_by) tuples, newest first.
        kicks: The total number of kicks for the member.
        kick_reasons: List of (entry_id, reason, timestamp, invoked_by) tuples, newest first.
        banned_from_testing: Whether the member is banned from testing.
        nicknames: List of (entry_id, nickname change, timestamp) tuples, newest first.

    The entry_id is the row's primary key in discordbot_mod_actions, which is
    what remove_user_entry() and edit_user_entry() take to target one row.
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
    nicknames: List[tuple] = field(default_factory=list)

    def entries(self, category: str) -> List[tuple]:
        return {
            "timeout": self.timeout_reasons,
            "ban": self.ban_reasons,
            "kick": self.kick_reasons,
            "name": self.nicknames,
        }[category]

    def __repr__(self):
        return (
            f"MemberInfo: Member name: ({self.member}, id: {self.member.id}), "
            f"Timeouts: {self.timeouts}, Total Bans: {self.bans}, Total Kicks: {self.kicks}, "
            f"Timeout Reasons: {self.timeout_reasons}, Ban Reasons: {self.ban_reasons}, Kick Reason {self.kick_reasons} "
            f"Nicknames {self.nicknames}"
        )


class ModeratorDB:
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.actions: dict[int, PendingAction] = {}

    async def fetch_user_info(self, member: Union[discord.User, discord.Member]) -> Optional[MemberInfo]:
        guild = self.bot.get_guild(Guilds.DDNET)
        member = await self.bot.get_or_fetch_member(guild=guild, user_id=member.id)
        if member is None:  # deleted account
            return None

        query = """
                SELECT id,
                       action,
                       reason,
                       timestamp,
                       invoked_by
                FROM discordbot_mod_actions
                WHERE user_id = %s
                  AND action IN ('ban', 'kick', 'timeout', 'nickname')
                ORDER BY timestamp DESC, id DESC
                """
        results = await self.bot.fetch(query, member.id, fetchall=True)

        timeout_reasons = []
        ban_reasons = []
        kick_reasons = []
        nicknames = []
        timeouts = bans = kicks = 0
        timeout = None

        for row in results:
            entry_id = row[0]
            action_type = row[1]
            action_reason = row[2]
            action_timestamp = row[3]
            action_invoked_by = row[4]

            if action_type == 'timeout':
                timeouts += 1
                timeout_reasons.append((entry_id, action_reason, action_timestamp, action_invoked_by))
            elif action_type == 'ban':
                bans += 1
                ban_reasons.append((entry_id, action_reason, action_timestamp, action_invoked_by))
            elif action_type == 'kick':
                kicks += 1
                kick_reasons.append((entry_id, action_reason, action_timestamp, action_invoked_by))
            elif action_type == "nickname":
                nicknames.append((entry_id, action_reason, action_timestamp))

        try:
            await guild.fetch_ban(member)
            currently_banned = True
        except discord.NotFound:
            currently_banned = False

        if isinstance(member, discord.Member) and member.timed_out_until:  # noqa
            timeout = member.timed_out_until  # noqa

        # testing bans
        query = """
                SELECT action
                FROM discordbot_mod_actions
                WHERE user_id = %s
                  AND action IN ('testing_ban', 'testing_unban')
                ORDER BY id DESC
                LIMIT 1
                """
        row = await self.bot.fetch(query, member.id)
        currently_banned_from_testing = bool(row) and row[0] == 'testing_ban'

        return MemberInfo(
            member=member,
            timed_out=timeout, timeouts=timeouts,
            timeout_reasons=timeout_reasons,
            banned=currently_banned, bans=bans, ban_reasons=ban_reasons,
            kicks=kicks, kick_reasons=kick_reasons,
            banned_from_testing=currently_banned_from_testing,
            nicknames=nicknames,
        )

    async def remove_user_entry(
            self,
            member: Union[discord.User, discord.Member],
            entry_type: str,  # 'timeout', 'ban', 'kick'
            entry_id: int,
    ) -> int:
        query = """
                DELETE
                FROM discordbot_mod_actions
                WHERE id = %s
                  AND user_id = %s
                  AND action = %s
                """
        return await self.bot.upsert(query, entry_id, member.id, entry_type)

    async def edit_user_entry(
            self,
            member: Union[discord.User, discord.Member],
            entry_type: str,  # 'timeout', 'ban', 'kick'
            entry_id: int,
            reason: str,
    ) -> int:
        query = """
                UPDATE discordbot_mod_actions
                SET reason = %s
                WHERE id = %s
                  AND user_id = %s
                  AND action = %s
                """
        return await self.bot.upsert(query, reason, entry_id, member.id, entry_type)

    async def log_action(
            self,
            invoker: discord.abc.User,
            user: discord.abc.User,
            action: ModAction,
            reason: str
    ):
        query = """
                INSERT INTO discordbot_mod_actions (user_id, action, reason, invoked_by)
                VALUES (%s, %s, %s, %s)
                """

        await self.bot.upsert(query, user.id, action.name.lower(), reason, invoker.name)

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
                INSERT INTO discordbot_mod_actions (user_id,
                                                    action,
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
                         FROM discordbot_mod_actions
                         WHERE action = 'ban' \
                         """
        rows = await self.bot.fetch(query_existing, fetchall=True)
        already_banned = {row[0] for row in rows}

        insert_query = """
                       INSERT INTO discordbot_mod_actions
                           (user_id, action, reason, invoked_by)
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
