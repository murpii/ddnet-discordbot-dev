import contextlib
import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from extensions.moderator.embeds import LogEmbed
from extensions.moderator.manager import ModAction, PendingAction
from extensions.moderator.views.info import ModeratorInfoButtons
from utils.misc import resolve_display_name
from constants import Guilds, Channels
from utils.text import to_discord_timestamp, human_timedelta

log = logging.getLogger()


class ModListeners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.moddb

    @staticmethod
    def convert_audit_action(
            entry: discord.AuditLogEntry,
    ) -> tuple[Optional[ModAction], Optional[datetime]]:
        """Translate a Discord audit log entry into an internal ModAction."""
        action = entry.action

        if action == discord.AuditLogAction.ban:
            return ModAction.BAN, None

        if action == discord.AuditLogAction.unban:
            return ModAction.UNBAN, None

        if action == discord.AuditLogAction.kick:
            return ModAction.KICK, None

        if action == discord.AuditLogAction.member_update:
            if not hasattr(entry.before, "timed_out_until"):
                return None, None

            before = entry.before.timed_out_until
            after = entry.after.timed_out_until
            now = discord.utils.utcnow()

            # timeout applied
            if after is not None and after > now and (before is None or before <= now):
                return ModAction.TIMEOUT, after

            # timeout removed
            if before is not None and before > now and (after is None or after <= now):
                return ModAction.UNTIMEOUT, None

            return None, None
        return None, None

    @staticmethod
    async def _resolve_nickname_invoker(
            before: discord.user,
            after: discord.user
    ) -> discord.abc.User | discord.Member:
        guild = after.guild
        with contextlib.suppress(discord.Forbidden):
            async for entry in guild.audit_logs(
                    limit=5,
                    action=discord.AuditLogAction.member_update,  # noqa
            ):
                if entry.target.id != after.id:
                    continue

                changes = entry.changes
                before_nick = getattr(changes.before, "nick", discord.utils.MISSING)
                after_nick = getattr(changes.after, "nick", discord.utils.MISSING)

                if before_nick is discord.utils.MISSING and after_nick is discord.utils.MISSING:
                    continue

                if before_nick == before.nick and after_nick == after.nick:
                    return entry.user

        return after

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        if entry.guild.id != Guilds.DDNET:
            return

        target = entry.target
        if not isinstance(target, (discord.Member, discord.User)):
            return

        action, timeout_expires_at = self.convert_audit_action(entry)
        if action is None:
            return

        invoker: discord.abc.User = entry.user
        reason: str = entry.reason or "No reason provided"

        pending: Optional[PendingAction] = self.bot.moddb.actions.pop(target.id, None)
        if isinstance(pending, PendingAction):
            invoker = pending.moderator
            action = pending.action
            reason = pending.reason

        actions: set[ModAction] = {
            ModAction.BAN,
            ModAction.KICK,
            ModAction.TIMEOUT,
            # ModAction.UNTIMEOUT and ModAction.UNBAN are intentionally skipped
        }

        if action in actions:
            await self.bot.moddb.log_action(invoker, target, action, reason)

        channel = (
                self.bot.get_channel(Channels.LOGS)
                or await self.bot.fetch_channel(Channels.LOGS)
        )
        if not channel:
            return

        verb_map: dict[ModAction, str] = {
            ModAction.BAN: "was banned",
            ModAction.UNBAN: "was unbanned",  # NEW
            ModAction.KICK: "was kicked",
            ModAction.TIMEOUT: "received a timeout",
            ModAction.UNTIMEOUT: "had their timeout removed",
        }
        verb = verb_map.get(action, f"received a {action.name.lower()}")

        timeout_line = ""
        if action is ModAction.TIMEOUT and timeout_expires_at is not None:
            timeout_line = (
                f"Timeout ends: "
                f"{to_discord_timestamp(timeout_expires_at, 'R')} "
                f"({to_discord_timestamp(timeout_expires_at, 'F')})\n"
            )

        message = (
            f"User {target.mention} {verb}.\n"
            f"{timeout_line}"
            f"Reason: {reason}\n"
            f"Invoked by: {invoker.mention}"
        )

        await channel.send(
            embed=LogEmbed(message, target),
            view=ModeratorInfoButtons(self.bot),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.guild.id != Guilds.DDNET:
            return

        if before.nick == after.nick:
            return

        invoker = await self._resolve_nickname_invoker(before, after)
        before_label = before.nick or resolve_display_name(before)  # noqa
        after_label = after.nick or resolve_display_name(after)  # noqa

        await self.bot.moddb.log_nickname_change(
            user=after,
            old=before_label,
            new=after_label,
            invoked_by=invoker,
        )

        channel = self.bot.get_channel(Channels.LOGS) or await self.bot.fetch_channel(Channels.LOGS)
        msg = (
            f"Member {after.mention} (`{after.id}`) changed nickname.\n"
            f"Nickname: `{before_label}` -> `{after_label}`\n"
            f"Invoked by: {invoker.mention}"
        )
        await channel.send(embed=LogEmbed(msg, after), view=ModeratorInfoButtons(self.bot))  # noqa

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # Compute a "display label" before/after
        before_label = before.global_name or before.name
        after_label = after.global_name or after.name

        # No effective change in what we display → ignore
        if before_label == after_label:
            return

        # We only care about users that are on the main guild
        guild = self.bot.get_guild(Guilds.DDNET)
        if guild is None:
            return

        member = guild.get_member(after.id)
        if member is None:
            try:
                member = await guild.fetch_member(after.id)
            except discord.NotFound:
                return  # not on the guild → ignore

        # Global name changes can only be done by the user themselves
        invoker = after

        await self.bot.moddb.log_nickname_change(
            member,
            old=before_label,
            new=after_label,
            invoked_by=invoker,
        )

        channel = self.bot.get_channel(Channels.LOGS) or await self.bot.fetch_channel(Channels.LOGS)
        msg = (
            f"Member {member.mention} (`{member.id}`) changed display name.\n"
            f"Nickname: `{before_label}` -> `{after_label}`\n"
            f"Invoked by: {invoker.mention}"
        )
        await channel.send(embed=LogEmbed(msg, member), view=ModeratorInfoButtons(self.bot))
