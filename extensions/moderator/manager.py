from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Union
import discord

from constants import Channels, Guilds
from extensions.moderator.embeds import LogEmbed


@dataclass
class MemberInfo:
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

    def __repr__(self):
        return (
            f"MemberInfo: Member name: ({self.member}, id: {self.member.id}), "
            f"Timeouts: {self.timeouts}, Total Bans: {self.bans}, Total Kicks: {self.kicks}, "
            f"Timeout Reasons: {self.timeout_reasons}, Ban Reasons: {self.ban_reasons}, Kick Reason {self.kick_reasons}"
        )


class ModeratorDB:
    def __init__(self, bot):
        self.bot = bot

    async def fetch_user_info(self, member: Union[discord.User, discord.Member]) -> Optional[MemberInfo]:
        try:
            if isinstance(member, discord.User):
                member = await self.bot.fetch_user(member.id)
            else:
                guild = self.bot.get_guild(Guilds.DDNET)
                if not guild.get_member(member.id):
                    return None
        except discord.NotFound:
            return None

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

        guild = self.bot.get_guild(Guilds.DDNET)
        banlist = [entry async for entry in guild.bans()]
        currently_banned = any((entry.user.id == member.id for entry in banlist))

        if (isinstance(member, discord.Member) and member.timed_out_until):
            timeout = member.timed_out_until

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
            invoked_by=action_invoked_by
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

    async def log_action(self, invoker: discord.abc.User, member: discord.abc.User, action: str, reason: str):
        member_info = await self.fetch_user_info(member) or MemberInfo(member=member)

        # Log the action into the new table with individual rows per action
        query = """
                INSERT INTO discordbot_user_info (user_id,
                                                  type,
                                                  reason,
                                                  invoked_by)
                VALUES (%s, %s, %s, %s)
                """
        await self.bot.upsert(query, member.id, action, reason, invoker.name)

        # Increment the counts (optional)
        if action == "ban":
            member_info.bans = (member_info.bans or 0) + 1
        elif action == "kick":
            member_info.kicks = (member_info.kicks or 0) + 1
        elif action == "timeout":
            member_info.timeouts = (member_info.timeouts or 0) + 1

        # Log the action to the log channel
        # TODO: Move this to the invoker func instead maybe
        channel = self.bot.get_channel(Channels.LOGS)
        if channel is None:
            channel = await self.bot.fetch_channel(Channels.LOGS)

        if channel:
            message = f"""
            User {member.mention} received a {action}. 
            Reason: {reason}
            Invoked by: {invoker.mention}
            
            Use ```/info user:{member.mention}``` to see full member history.
            """

            await channel.send(embed=LogEmbed(message, member))

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
