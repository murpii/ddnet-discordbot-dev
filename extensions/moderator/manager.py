from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union
import discord

from constants import Channels, Guilds


@dataclass
class MemberInfo:
    member: Union[discord.User, discord.Member]
    timeouts: int = None
    timeout_reasons: List[tuple] = field(default_factory=list)
    bans: int = None
    ban_reasons: List[tuple] = field(default_factory=list)
    kicks: int = None
    kick_reasons: List[tuple] = field(default_factory=list)
    banned_from_testing: bool = False
    invoked_by: str = "Unknown"

    def __repr__(self):
        return (
            f"MemberInfo: Member name: ({self.member}, id: {self.member.id}), "
            f"Timeouts: {self.timeouts}, Total Bans: {self.bans}, Total Kicks: {self.kicks}, "
            f"Timeout Reasons: {self.timeout_reasons}, Ban Reasons: {self.ban_reasons}, Kick Reason {self.kick_reasons}"
        )


class ModManager:
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def embed(member_info: MemberInfo) -> Optional[discord.Embed]:
        if not member_info:
            return discord.Embed(
                title="User Info",
                description="No user information found.",
                color=discord.Color.red(),
            )

        # ---------------------------------------------------
        # Header
        # ---------------------------------------------------

        embed = discord.Embed(title=":crossed_swords: User Info", color=discord.Color.blurple())
        embed.set_thumbnail(url=member_info.member.display_avatar.url)

        embed.add_field(
            name="Name",
            value=f"{member_info.member.mention}", # (ID: {member_info.member.id})
            inline=False
        )

        embed.add_field(
            name="Created At",
            value=f"{member_info.member.created_at.strftime('`%Y-%m-%d`')}\n`{member_info.member.created_at.strftime('%H:%M UTC')}`",
            inline=True,
        )

        embed.add_field(
            name="Joined At",
            value=f"{member_info.member.joined_at.strftime('`%Y-%m-%d`')}\n`{member_info.member.joined_at.strftime('%H:%M UTC')}`"
            if hasattr(member_info.member, 'joined_at') else "`Unknown`",
            inline=True
        )

        # ---------------------------------------------------
        # Timeouts
        # ---------------------------------------------------

        if member_info.timeouts:
            if member_info.timeout_reasons:
                timeout_reasons = "\n".join(
                    f"[`{reason_time[1].strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason_time[0]}"
                    for reason_time in member_info.timeout_reasons
                )
            else:
                timeout_reasons = "No reasons provided"

            timeout_str = f" Total Timeouts: {member_info.timeouts} "

            embed.add_field(
                name=f"{timeout_str.center(32, '─')}",
                value=f"{timeout_reasons}",
                inline=False
            )
        else:
            embed.add_field(name="Total Timeouts", value="No timeouts found.", inline=False)

        # ---------------------------------------------------
        # Bans
        # ---------------------------------------------------

        if member_info.bans:
            if member_info.ban_reasons:
                ban_reasons = "\n".join(
                    f"[`{reason_time[1].strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason_time[0]}"
                    for reason_time in member_info.ban_reasons
                )
            else:
                ban_reasons = "No reasons provided"

            ban_str = f" Total Bans: {member_info.bans} "

            embed.add_field(
                name=f"{ban_str.center(32, '─')}",
                value=f"{ban_reasons}",
                inline=False
            )
        else:
            embed.add_field(name="Bans", value="No bans found.", inline=False)

        # ---------------------------------------------------
        # Kicks
        # ---------------------------------------------------

        if member_info.kicks:
            if member_info.kick_reasons:
                kick_reasons = "\n".join(
                    f"[`{reason_time[1].strftime('%Y-%m-%d %H:%M')}`] {member_info.invoked_by} › {reason_time[0]}"
                    for reason_time in member_info.kick_reasons
                )
            else:
                kick_reasons = "No reasons provided"

            kick_str = f" Total Kicks: {member_info.kicks} "

            embed.add_field(
                name=f"{kick_str.center(32, '─')}",
                value=f"{kick_reasons}",
                inline=False
            )
        else:
            embed.add_field(name="Kicks", value="No kicks found.", inline=False)

        return embed

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
        SELECT
            type,
            reason,
            timestamp,
            invoked_by
        FROM
            discordbot_user_info
        WHERE
            user_id = %s
        """

        results = await self.bot.fetch(query, member.id, fetchall=True)

        timeout_reasons = []
        ban_reasons = []
        kick_reasons = []
        timeouts = bans = kicks = 0
        action_banned_from_testing = False
        action_invoked_by = "Unknown"

        # TODO: Maybe just use count instead

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

        return MemberInfo(
            member=member,
            timeouts=timeouts,
            timeout_reasons=timeout_reasons,
            bans=bans,
            ban_reasons=ban_reasons,
            kicks=kicks,
            kick_reasons=kick_reasons,
            banned_from_testing=action_banned_from_testing,
            invoked_by=action_invoked_by
        )

    async def log_action(self, invoker: discord.Member, member: Union[discord.User, discord.Member], action: str, reason: str):
        member_info = await self.fetch_user_info(member) or MemberInfo(member=member)

        # Log the action into the new table with individual rows per action
        query = """
        INSERT INTO discordbot_user_info (
            user_id,
            type,
            reason,
            invoked_by
        ) 
        VALUES 
            (%s, %s, %s, %s)
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

            embed = discord.Embed(
                title=":crossed_swords: Discord Moderation",
                color=discord.Color.blurple(),
                timestamp=datetime.now(),
                description=message
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)