import asyncio
import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

from extensions.management.moderator.manager import PendingAction, ModAction
from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
from utils.misc import history, DELETE_HISTORY_SECONDS
from utils.text import choice_to_timedelta
from utils.checks import staff_only
from constants import Guilds

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()


def slow_mode_choices() -> list:
    return [
        app_commands.Choice(name="5 minutes", value=0),
        app_commands.Choice(name="10 minutes", value=1),
        app_commands.Choice(name="30 minutes", value=2),
        app_commands.Choice(name="1 hour", value=3),
        app_commands.Choice(name="2 hours", value=4),
    ]


# TODO: Add changelogs for every command.
class ModAppCommands(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

    timeout_group = app_commands.Group(
        name="timeout",
        description="Toggle a timeout on a user for a number of minutes, with an optional message.",
        guild_ids=[int(Guilds.DDNET)],
    )

    kick_group = app_commands.Group(
        name="kick",
        description="Kicks a user either by their ID or by mentioning them.",
        guild_ids=[int(Guilds.DDNET)],
    )

    ban_group = app_commands.Group(
        name="ban",
        description="Bans a user either by their ID or by mentioning them.",
        guild_ids=[int(Guilds.DDNET)],
    )

    unban_group = app_commands.Group(
        name="unban",
        description="Unbans a user either by their ID or by mentioning them.",
        guild_ids=[int(Guilds.DDNET)],
    )

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.command(name="slowmode", description="Toggles slow mode for the current channel.")
    @app_commands.describe(
        for_how_long="The time slow mode should stay active (optional)",
        slow_duration="Set how long each user must wait between messages (in seconds, 0 to disable)"
    )
    @app_commands.choices(for_how_long=slow_mode_choices())
    @staff_only()
    async def toggle_slow_mode(self, interaction: discord.Interaction, slow_duration: int, for_how_long: int = None):
        channel = interaction.channel

        await channel.edit(slowmode_delay=slow_duration)
        log.info(
            f"Slow mode enabled in {channel.name} (Guild: {interaction.guild.name}) by user: {interaction.user.name}"
        )

        if slow_duration == 0:
            message = f"Slow mode disabled in {channel.mention}."
        else:
            message = f"Slow mode enabled in {channel.mention} with {slow_duration} seconds delay."

        if for_how_long is not None:
            disable_time, duration_str = choice_to_timedelta(for_how_long)
            message += f" It will be disabled automatically after {duration_str}."
            await interaction.response.send_message(content=message, ephemeral=True)
            await asyncio.sleep(disable_time)
            await channel.edit(slowmode_delay=0)
            log.info(f"Slow mode has been disabled automatically in {channel.mention}.")
        else:
            await interaction.response.send_message(content=message, ephemeral=True)

    @timeout_group.command(
        name="user",
        description="Timeout a user for a number of minutes, with an optional message."
    )
    @staff_only("mods")
    @app_commands.describe(
        member="The member to timeout.",
        minutes="The number of minutes to timeout the member for.",
        reason="The reason for the timeout.")
    async def timeout_user(
            self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str
    ):
        await interaction.response.defer(ephemeral=True)

        if member.timed_out_until and member.timed_out_until > datetime.datetime.now(datetime.timezone.utc):
            await interaction.followup.send(
                f"{member.mention} is already timed out. "
                f"Will be cleared in <t:{int(member.timed_out_until.timestamp())}:R>."
            )
            return

        self.bot.moddb.actions[member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.TIMEOUT,
            reason=reason,
        )
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await interaction.followup.send(
            f"User {member.mention} has been timed out for {minutes} minutes. Reason: {reason}"
        )

    @timeout_group.command(name="remove", description="Remove timeout from a user.")
    @staff_only("mods")
    @app_commands.describe(
        member="The member to remove timeout from.")
    async def remove_timeout(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if not member.timed_out_until or member.timed_out_until <= datetime.datetime.now(datetime.timezone.utc):
            await interaction.followup.send(f"{member.mention} is not currently timed out.")
            return

        await member.timeout(None, reason="Timeout removed by staff")
        await interaction.followup.send(f"Timeout has been removed for user {member.mention}.")

    @kick_group.command(name="user", description="Kick a user by mentioning them.")
    @staff_only("discord_mods")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        member="The user to kick.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for the kick.")
    async def kick_member(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
            delete_message_history: app_commands.Choice[int],
            reason: str,
    ):
        # Using guild.ban allows to mass delete messages from a user. The user is unbanned right after.
        await interaction.response.defer(ephemeral=True)

        self.bot.moddb.actions[member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.KICK,
            reason=reason,
        )

        await interaction.guild.ban(
            member,
            delete_message_seconds=DELETE_HISTORY_SECONDS[delete_message_history.value],
            reason=reason,
        )
        await interaction.guild.unban(member)
        await interaction.followup.send(f"User {member.mention} has been kicked. Reason: {reason}")

    @kick_group.command(name="id", description="Kicks a user by their ID.")
    @staff_only("discord_mods")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        ident="The users ID to kick.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for the kick.")
    async def kick_user_id(
            self,
            interaction: discord.Interaction,
            ident: str,
            delete_message_history: app_commands.Choice[int],
            reason: str,
    ):
        await interaction.response.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(ident))
        member = interaction.guild.get_member(user.id)
        if member is None:
            await interaction.followup.send(f"User with ID: `{ident}` is not in the server.")
            return

        # Using guild.ban allows to mass delete messages from a user. The user is unbanned right after.
        self.bot.moddb.actions[member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.KICK,
            reason=reason,
        )
        await interaction.guild.ban(
            user,
            delete_message_seconds=DELETE_HISTORY_SECONDS[delete_message_history.value],
            reason=reason,
        )
        await interaction.guild.unban(user)
        await interaction.followup.send(
            f"User {user.mention} (ID: `{ident}`) has been kicked. Reason: {reason}"
        )

    @ban_group.command(name="user", description="Bans a user by mentioning them.")
    @staff_only("discord_mods")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        user="The user to ban.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for banning"
    )
    async def ban_user(
            self,
            interaction: discord.Interaction,
            user: discord.User,
            delete_message_history: app_commands.Choice[int],
            reason: str,
    ):
        await interaction.response.defer(ephemeral=True)

        # Single ban lookup; NotFound means the user isn't banned yet.
        try:
            await interaction.guild.fetch_ban(user)
        except discord.NotFound:
            pass  # not banned, proceed
        except discord.Forbidden:
            await interaction.followup.send(
                "I do not have permission to view bans. This is required to check if the person is already banned."
            )
            return
        except discord.HTTPException:
            await interaction.followup.send("HTTPException: Failed to check if user is banned. Try again later.")
            return
        else:
            await interaction.followup.send(f"{user.mention} (ID: `{user.id}`) is already banned.")
            return

        self.bot.moddb.actions[user.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.BAN,
            reason=reason,
        )
        await interaction.guild.ban(
            user,
            delete_message_seconds=DELETE_HISTORY_SECONDS[delete_message_history.value],
            reason=reason,
        )
        await interaction.followup.send(f"User {user.mention} has been banned for \"{reason}\"")

    @ban_group.command(name="id", description="Bans a user by their ID.")
    @staff_only("discord_mods")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        ident="The user's ID to ban.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for banning")
    async def ban_user_id(
            self,
            interaction: discord.Interaction,
            ident: str,
            delete_message_history: app_commands.Choice[int],
            reason: str,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            user = await self.bot.fetch_user(int(ident))
        except discord.NotFound:
            await interaction.followup.send(f"Could not find user with ID: `{ident}`.")
            return

        # Single ban lookup; NotFound means the user isn't banned yet.
        try:
            await interaction.guild.fetch_ban(user)
        except discord.NotFound:
            pass  # not banned, proceed
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to view bans.")
            return
        except discord.HTTPException:
            await interaction.followup.send("HTTPException: Failed to check if user is banned. Try again later.")
            return
        else:
            await interaction.followup.send(f"{user.mention} (ID: `{ident}`) is already banned.")
            return

        self.bot.moddb.actions[user.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.BAN,
            reason=reason,
        )
        await interaction.guild.ban(
            user,
            delete_message_seconds=DELETE_HISTORY_SECONDS[delete_message_history.value],
            reason=reason,
        )
        await interaction.followup.send(
            f"User {user.mention} (ID: `{ident}`) has been banned for \"{reason}\""
        )

    @unban_group.command(name="user", description="Unbans a user by mentioning them.")
    @staff_only("discord_mods")
    @app_commands.describe(user="The user to unban.")
    async def unban_user(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.guild.unban(user)
            await interaction.followup.send(f"User {user.mention} has been unbanned.")
        except discord.NotFound:
            await interaction.followup.send(f"User {user.mention} isn't banned.")

    @unban_group.command(name="id", description="Unbans a user by their ID.")
    @staff_only("discord_mods")
    @app_commands.describe(ident="The user ID to unban.")
    async def unban_user_id(self, interaction: discord.Interaction, ident: str):
        await interaction.response.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(ident))

        try:
            await interaction.guild.unban(user)
            await interaction.followup.send(f"User {user.mention} has been unbanned.")
        except discord.NotFound:
            await interaction.followup.send(f"User {user.mention} isn't banned.")

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.command(name="info", description="Sends user infos from database")
    @staff_only("mods")
    @app_commands.describe(user="The member")
    async def info_user(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        info = await self.bot.moddb.fetch_user_info(user)

        if not info:
            await interaction.followup.send(view=NoUserInfoView())
            return

        await interaction.followup.send(view=UserInfoView(self.bot, info, interaction.user))
