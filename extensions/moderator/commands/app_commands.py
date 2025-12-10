import asyncio
import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

from extensions.moderator.embeds import NoMemberInfoEmbed, full_info
from extensions.moderator.manager import PendingAction, ModAction
from utils.misc import history
from utils.text import choice_to_timedelta
from utils.checks import is_staff, ddnet_only
from constants import Guilds, Roles

log = logging.getLogger()
seconds_list = [0, 3600, 21600, 43200, 86400, 259200, 604800]


# TODO: Add changelogs for every command.
class ModAppCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def slow_mode_choices() -> list:
        return [
            app_commands.Choice(name="5 minutes", value=0),
            app_commands.Choice(name="10 minutes", value=1),
            app_commands.Choice(name="30 minutes", value=2),
            app_commands.Choice(name="1 hour", value=3),
            app_commands.Choice(name="2 hours", value=4),
        ]

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.command(name="slowmode", description="Toggles slow mode for the current channel.")
    @app_commands.describe(
        for_how_long="The time slow mode should stay active (optional)",
        slow_duration="Set how long each user must wait between messages (in seconds, 0 to disable)"
    )
    @app_commands.choices(for_how_long=slow_mode_choices())
    async def toggle_slow_mode(self, interaction: discord.Interaction, slow_duration: int, for_how_long: int = None):
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "You are missing the required roles to use this command.",
                ephemeral=True
            )
            return

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

    @commands.hybrid_group(
        name="timeout",
        with_app_command=True,
        description="Toggle a timeout on a user for a number of minutes, with an optional message. "
    )
    @commands.check(ddnet_only)
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    async def timeout_group(self, ctx):
        pass

    @timeout_group.command(
        name="user",
        with_app_command=True,
        description="Timeout a user for a number of minutes, with an optional message.",
        usage="$timeout <@mention> <minutes> <reason>")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.describe(
        member="The member to timeout.",
        minutes="The number of minutes to timeout the member for.",
        reason="The reason for the timeout.")
    async def timeout_user(self, ctx, member: discord.Member, minutes: int, *, reason: str):
        if not ctx.guild or member.guild != ctx.guild:
            await ctx.send("That user is not a member of this server.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        if member.timed_out_until and member.timed_out_until > datetime.datetime.now(datetime.timezone.utc):
            await ctx.send(
                f"{member.mention} is already timed out. "
                f"Will be cleared in <t:{int(member.timed_out_until.timestamp())}:R>."
            )
            return

        self.bot.moddb.actions[member.id] = PendingAction(
            moderator=ctx.user,
            action=ModAction.TIMEOUT,
            reason=reason,
        )
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await ctx.send(f"User {member.mention} has been timed out for {minutes} minutes. Reason: {reason}")

    @timeout_group.command(
        name="remove",
        with_app_command=True,
        description="Remove timeout from a user.",
        usage="$timeout remove <@mention>")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.describe(
        member="The member to remove timeout from.")
    async def remove_timeout(self, ctx, member: discord.Member):
        await ctx.defer(ephemeral=True)

        if not member.timed_out_until or member.timed_out_until <= datetime.datetime.now(datetime.timezone.utc):
            await ctx.send(f"{member.mention} is not currently timed out.")
            return

        await member.timeout(None, reason="Timeout removed by staff")
        await ctx.send(f"Timeout has been removed for user {member.mention}.")

    @commands.hybrid_group(
        name="kick",
        with_app_command=True,
        description="Kicks a user either by their ID or by mentioning them.")
    @commands.check(ddnet_only)
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    async def kick_group(self, ctx):
        pass

    @kick_group.command(
        name="user",
        with_app_command=True,
        description="Kick a user by mentioning them.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        member="The user to kick.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for the kick.")
    async def kick_member(
            self, ctx, member: discord.Member, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        # Using guild.ban allows to mass delete messages from a user. The user is unbanned right after.
        await ctx.defer(ephemeral=True)

        if member is None:
            await ctx.send("Member is no longer in the server.")
            return

        self.bot.moddb.actions[member.id] = PendingAction(
            moderator=ctx.user,
            action=ModAction.KICK,
            reason=reason,
        )

        await ctx.guild.ban(member, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.guild.unban(member)
        await ctx.send(f"User {member.mention} has been kicked. Reason: {reason}")

    @kick_group.command(
        name="id",
        with_app_command=True,
        description="Kicks a user by their ID.")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        ident="The users ID to kick.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for the kick.")
    async def kick_user_id(
            self, ctx, ident: str, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        await ctx.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(ident))
        member = ctx.guild.get_member(user.id)
        if member is None:
            await ctx.send(f"User with ID: `{ident}` is not in the server.")
            return

        # Using guild.ban allows to mass delete messages from a user. The user is unbanned right after.
        self.bot.moddb.actions[member.id] = (ctx.author, "kick", reason)
        await ctx.guild.ban(user, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.guild.unban(user)
        await ctx.send(f"User {user.mention} (ID: `{ident}`) has been kicked. Reason: {reason}")

    @commands.hybrid_group(
        name="ban",
        with_app_command=True,
        description="Bans a user either by their ID or by mentioning them.")
    @commands.check(ddnet_only)
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    async def ban_group(self, ctx):
        pass

    @ban_group.command(name="user", with_app_command=True, description="Bans a user by mentioning them.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        user="The user to ban.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for banning"
    )
    async def ban_user(
            self, ctx, user: discord.User, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        await ctx.defer(ephemeral=True)

        try:
            bans = await ctx.guild.bans()
            if any(ban_entry.user.id == user.id for ban_entry in bans):
                await ctx.send(f"{user.mention} (ID: `{user.id}`) is already banned.")
                return
        except discord.Forbidden:
            await ctx.send(
                "I do not have permission to view bans. This is required to check if the person is already banned."
            )
            return
        except discord.HTTPException:
            await ctx.send("HTTPException: Failed to check if user is banned. Try again later.")
            return

        self.bot.moddb.actions[user.id] = (ctx.author, "ban", reason)
        await ctx.guild.ban(user, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.send(f"User {user.mention} has been banned for \"{reason}\"")

    @ban_group.command(name="id", with_app_command=True, description="Bans a user by their ID.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        ident="The user's ID to ban.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for banning")
    async def ban_user_id(
            self, ctx, ident: str, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        await ctx.defer(ephemeral=True)

        try:
            user = await self.bot.fetch_user(int(ident))
        except discord.NotFound:
            await ctx.send(f"Could not find user with ID: `{ident}`.")
            return

        try:
            async for ban_entry in ctx.guild.bans():
                if ban_entry.user.id == user.id:
                    await ctx.send(f"{user.mention} (ID: `{ident}`) is already banned.")
                    return
        except discord.Forbidden:
            await ctx.send("I do not have permission to view bans.")
            return
        except discord.HTTPException:
            await ctx.send("HTTPException: Failed to check if user is banned. Try again later.")
            return

        self.bot.moddb.actions[user.id] = (ctx.author, "ban", reason)
        await ctx.guild.ban(user, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.send(f"User {user.mention} (ID: `{id}`) has been banned for \"{reason}\"")

    @commands.hybrid_group(name="unban", with_app_command=True)
    @commands.check(ddnet_only)
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    async def unban_group(self, ctx):
        pass

    @unban_group.command(name="user", with_app_command=True, description="Unbans a user by mentioning them.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.describe(user="The user to unban.")
    async def unban_user(self, ctx, user: discord.User):
        await ctx.defer(ephemeral=True)

        try:
            await ctx.guild.unban(user)
            await ctx.send(f"User {user.mention} has been unbanned.")
        except discord.NotFound:
            await ctx.send(f"User {user.mention} isn't banned.")

    @unban_group.command(name="id", with_app_command=True, description="Unbans a user by their ID.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.describe(ident="The user ID to unban.")
    async def unban_user_id(self, ctx, ident: str):
        await ctx.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(ident))

        try:
            await ctx.guild.unban(user)
            await ctx.send(f"User {user.mention} has been unbanned.")
        except discord.NotFound:
            await ctx.send(f"User {user.mention} isn't banned.")

    @commands.hybrid_command(
        name="info",
        with_app_command=True,
        description="Sends user infos from database",
        usage="$info <userID/@mention>")
    @commands.check(ddnet_only)
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR, Roles.MODERATOR)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.describe(user="The member")
    async def info_user(self, ctx, user: discord.User):
        await ctx.defer(ephemeral=True)
        info = await self.bot.moddb.fetch_user_info(user)

        if not info:
            await ctx.send(embed=NoMemberInfoEmbed())
            return

        await ctx.send(embeds=full_info(info))

    @commands.command()
    @commands.check(ddnet_only)
    @commands.has_permissions(administrator=True)
    async def import_bans(self, ctx):
        string = await self.bot.moddb.import_existing_bans(ctx.guild)
        await ctx.send(string)
