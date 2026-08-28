import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from constants import Channels, Guilds, Roles
from utils.checks import is_staff
from utils.containers import ALERT_ACCENT, NoticeView
from utils.misc import log_to
from extensions.management.tester import queries

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

# channels considered "testing" by the ban system and the channel tools.
TESTING_CATEGORIES = (Channels.CAT_TESTING, Channels.CAT_WAITING, Channels.CAT_EVALUATED)

# users holding any of these cannot be banned from testing.
PROTECTED_ROLES = [
    Roles.ADMIN, Roles.MODERATOR, Roles.DISCORD_MODERATOR,
    Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
    Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
]


@dataclass
class TestingBan:
    user_id: int
    user_name: str
    banned_by: int
    reason: str
    timestamp: int


class TesterBans(commands.Cog):
    """
    Testing-category ban system.

    A testing ban hides the entire testing area from one member and keeps it
    hidden if they leave and rejoin.

    Bookkeeping lives in the shared moderation audit log discordbot_mod_actions (see queries.py)
    """

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.active: dict[int, TestingBan] = {}
        self.setup = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self.setup:
            return
        self.setup = True

        await self.load_bans()
        log.info("TesterBans: %d active testing bans loaded", len(self.active))

    async def load_bans(self) -> None:
        guild = self.bot.get_guild(Guilds.DDNET)
        rows = await self.bot.fetch(queries.SELECT_ACTIVE_BANS, fetchall=True)

        self.active = {}
        for user_id, invoked_by, reason, timestamp in rows:
            user = await self.bot.get_or_fetch_member(guild=guild, user_id=user_id)
            self.active[user_id] = TestingBan(
                user_id=user_id,
                user_name=user.name if user else str(user_id),
                banned_by=int(invoked_by),
                reason=reason or "No reason provided",
                timestamp=int(timestamp),
            )

    def ban_targets(self, guild: discord.Guild) -> list:
        """
        The testing categories plus every channel inside them that does
        not sync its permissions
        """
        targets = []
        for category_id in TESTING_CATEGORIES:
            category = guild.get_channel(category_id)
            if category is None:
                continue
            targets.append(category)
            targets.extend(c for c in category.channels if not c.permissions_synced)
        return targets

    async def apply_ban_overwrites(self, member: discord.Member) -> None:
        for target in self.ban_targets(member.guild):
            overwrite = target.overwrites_for(member)
            overwrite.view_channel = False
            await target.set_permissions(member, overwrite=overwrite, reason="Banned from testing")

    async def remove_ban_overwrites(self, guild: discord.Guild, user_id: int) -> None:
        user = await self.bot.get_or_fetch_member(guild=guild, user_id=user_id)
        if user is None:  # deleted account
            return
        for target in self.ban_targets(guild):
            if any(holder.id == user_id for holder in target.overwrites):
                await target.set_permissions(user, overwrite=None, reason="Testing ban lifted")

    async def ban(self, member, *, banned_by: discord.Member, reason: str) -> str:
        """Bans (duh) a member from testing"""
        if not isinstance(member, discord.Member):
            return "That user is not on this server."
        if member.bot:
            return "Bots cannot be banned from testing."
        if member.id in self.active:
            return f"{member.mention} is already banned from testing."
        if is_staff(member, roles=PROTECTED_ROLES):
            return f"{member.mention} is staff and cannot be banned from testing."

        try:
            await self.apply_ban_overwrites(member)
            testing_role = member.guild.get_role(Roles.TESTING)
            if testing_role and testing_role in member.roles:
                await member.remove_roles(testing_role, reason="Banned from testing")
        except discord.Forbidden:
            return "I am not allowed to edit the testing channel permissions."

        await self.bot.upsert(queries.INSERT_ACTION, member.id, "testing_ban", reason, banned_by.id)
        self.active[member.id] = TestingBan(
            user_id=member.id,
            user_name=member.name,
            banned_by=banned_by.id,
            reason=reason,
            timestamp=int(time.time()),
        )

        log.info("TesterBans: %s banned %s from testing: %s", banned_by, member, reason)
        await self.notify_logs(f"{banned_by.mention} banned {member.mention} from testing: {reason}")
        return f"{member.mention} is now banned from testing."

    async def unban(self, user_id: int, *, unbanned_by: discord.Member) -> str:
        """Lifts a testing ban"""
        ban_entry = self.active.get(user_id)
        if ban_entry is None:
            return "That user is not banned from testing."

        guild = self.bot.get_guild(Guilds.DDNET)
        try:
            await self.remove_ban_overwrites(guild, user_id)
        except discord.Forbidden:
            return "I am not allowed to edit the testing channel permissions."

        await self.bot.upsert(queries.INSERT_ACTION, user_id, "testing_unban", None, unbanned_by.id)
        del self.active[user_id]

        log.info("TesterBans: %s lifted the testing ban of %s", unbanned_by, ban_entry.user_name)
        await self.notify_logs(f"{unbanned_by.mention} lifted the testing ban of <@{user_id}>.")
        return f"<@{user_id}> is no longer banned from testing."

    async def notify_logs(self, text: str) -> None:
        await log_to(
            self.bot, Channels.LOG_MOD_ACTIONS,
            view=NoticeView(text, accent=ALERT_ACCENT),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != Guilds.DDNET or member.bot:
            return
        if member.id in self.active:
            try:
                await self.apply_ban_overwrites(member)
            except discord.Forbidden:
                log.warning("TesterBans: could not re-apply the testing ban of %s", member)
