import asyncio
import hashlib
import re
import contextlib
import time
from collections import defaultdict
from typing import Optional

from requests_cache import CachedSession
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from .views.links import ButtonLinks
from .embeds import (
    NoMemberInfoEmbed, MemberInfoEmbed, TimeoutsEmbed,
    BansEmbed, KicksEmbed, ServerInfoEmbed, NoEntries
)
from .manager import ModeratorDB
from utils.text import choice_to_timedelta
from utils.checks import is_staff
from constants import Guilds, Channels, Roles
from data.countryflags import COUNTRYFLAGS
from constants import Emojis

# If the bot is running into KeyErrors, use /clear_cache to clear the sqlite cache the bot uses.
session = CachedSession(cache_name="data/cache", expire_after=60 * 60 * 2)
log = logging.getLogger()
seconds_list = [0, 3600, 21600, 43200, 86400, 259200, 604800]


def hash_message(message: discord.Message):
    """Generate a hash based on content and attachments."""
    hasher = hashlib.sha256()
    hasher.update(message.content.encode('utf-8'))
    for att in message.attachments:
        hasher.update(att.url.encode('utf-8'))
    return hasher.hexdigest()


def source(url):
    resp = session.get(url)
    return resp.json()


def history() -> list:
    return [
        app_commands.Choice(name="Don't Delete Any", value=0),
        app_commands.Choice(name="Previous Hour", value=1),
        app_commands.Choice(name="Previous 6 Hours", value=2),
        app_commands.Choice(name="Previous 12 Hours", value=3),
        app_commands.Choice(name="Previous 24 Hours", value=4),
        app_commands.Choice(name="Previous 3 Days", value=5),
        app_commands.Choice(name="Previous 7 Days", value=6)
    ]


def ddnet_only(ctx: commands.Context) -> bool:
    return ctx.guild.id == Guilds.DDNET


def extract_address(string: str) -> Optional[str]:
    pattern = r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5})"
    return match.group(1) if (match := re.search(pattern, string)) else None


def flag(ident) -> str:
    return next(
        (COUNTRYFLAGS[key] for key in COUNTRYFLAGS.keys() if key[0] == ident),
        f"<:flag_unk:{Emojis.FLAG_UNK}>",
    )


def parse_community_info(resp):
    """
    Extract community information from the response data.

    Args:
    - resp: The response object containing community data.

    Returns:
    - A dictionary where each key is a community ID and the value is another dictionary
      containing the community's name and contact URLs.
    """
    return {
        community["id"]: {
            "name": community["name"],
            "contact_urls": community.get("contact_urls", ""),
            "url": community.get("icon", {}).get("url"),
        }
        for community in resp.get("communities", [])
    }


def find_server_info_by_type(resp, addr, community_info, server_key):
    for server in resp.get(server_key, []):
        for server_type, addresses in server.get("servers", {}).items():
            if isinstance(addresses, list) and addr in addresses:
                community_id = "ddnet" if server_key == "servers" else "kog"
                return {
                    "network": community_info[community_id]["name"],
                    "name": community_info[community_id]["name"],
                    "contact_url": community_info[community_id]["contact_urls"],
                    "server_type": server_type,
                    "flagId": server.get("flagId"),
                    "icon": community_info[community_id].get("url")
                }
    return None


# TODO: This needs changing in the future
def find_server_info_by_icon(resp, addr, community_info):
    for community in resp.get("communities", []):
        if "icon" in community and "servers" in community["icon"]:
            for server in community["icon"]["servers"]:
                for server_type, addresses in server.get("servers", {}).items():
                    if isinstance(addresses, list) and addr in addresses:
                        return {
                            "network": community_info[community["id"]]["name"],
                            "name": community_info[community["id"]]["name"],
                            "contact_url": community_info[community["id"]]["contact_urls"],
                            "server_type": server_type,
                            "flagId": server.get("flagId"),
                            "icon": community_info[community["id"]]["url"]
                        }
    return None


def fetch_server_info(addr):
    """
    Retrieve information about a server based on its address.

    Args:
    - addr: The address of the server to fetch information for.

    Returns:
    - A dictionary containing server information, or an empty dictionary if no information is found.
    """

    resp = source("https://info.ddnet.org/info")
    community_info = parse_community_info(resp)

    server_info = find_server_info_by_type(resp, addr, community_info, "servers")
    if server_info:
        return server_info

    server_info = find_server_info_by_type(
        resp, addr, community_info, "servers-kog"
    )
    if server_info:
        return server_info

    server_info = find_server_info_by_icon(resp, addr, community_info)
    return server_info or {}


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_cache = {}
        self.mod_call = []
        self.timeout = datetime.timedelta(minutes=1)
        self.edited_with_mentions = set()
        self.user_messages = defaultdict(list)
        self.alerted = defaultdict(set)

    async def discord_resp(self, addr: str, channel: discord.TextChannel):
        """|coro|
        Retrieves server details, constructs an embed and view for Discord, and determines the network name.

        Args:
            addr (str): The address of the server to look up.
            channel (discord.TextChannel): The channel where the information will be displayed.

        Returns:
            Tuple[discord.Embed, Optional[ButtonLinks], Optional[str]]: The embed to display, an optional view, and the network name if available.
        """
        info = fetch_server_info(addr)

        if not info:
            embed = ServerInfoEmbed.from_server_info(
                info=None,
                addr=addr,
            )
            return embed, None, None

        contact_list: list = info.get("contact_url")
        contact_url = None
        if contact_list:
            for url in contact_list:
                try:
                    if url.startswith("https://discord.gg/"):
                        await self.bot.fetch_invite(url)
                        contact_url = url
                        break
                except discord.errors.NotFound:
                    continue
                except (TypeError, IndexError):
                    continue

        view = None
        region = flag(info.get("flagId"))
        ticket = self.bot.ticket_manager.tickets.get(channel.id)
        is_ticket = ticket is not None
        view = ButtonLinks(is_ticket, addr, info.get("network"), contact_url)

        embed = ServerInfoEmbed.from_server_info(
            addr=addr,
            info=info,
            ticket=is_ticket,
            region=region,
        )

        return embed, view, info.get("network")

    @commands.Cog.listener("on_message")
    async def address_verify(self, message: discord.Message):
        """
        This method checks if a message contains a valid server address and sends a response if it does.
        """
        if (
                message.guild is None
                or message.author.bot
                or message.guild.id != Guilds.DDNET
        ):
            return

        # clear codeblocks from message.content
        pattern = r"```(?:\w+\n)?([\s\S]+?)```|`(?:\w+)?(.+?)`"
        content = re.sub(pattern, "", message.content, flags=re.DOTALL)

        addr = extract_address(content)
        if not addr:
            return

        with contextlib.suppress(discord.Forbidden):
            embed, view, network = await self.discord_resp(addr, message.channel)

        if (
                message.channel.name.startswith("report-")
                and network == "DDraceNetwork"
                and message.channel not in self.mod_call
        ):
            self.mod_call.append(message.channel)
            msg = await message.channel.send(content=f"<@&{Roles.MODERATOR}>", embed=embed, view=view)
            self.message_cache[message.id] = msg.id
            return

        if view:
            msg = await message.channel.send(embed=embed, view=view)
        else:
            msg = await message.channel.send(embed=embed)

        self.message_cache[message.id] = msg.id

    @commands.Cog.listener("on_message_edit")
    async def message_edit(self, before: discord.Message, after: discord.Message):
        """
        Handle the editing of messages to verify and respond to server addresses.

        This method checks if the edited message contains a server address and responds accordingly.
        If the message is in a report channel and contains a valid address, it will notify moderators
        and update the message content with relevant information.

        Args:
        - before: The message object before the edit.
        - after: The message object after the edit.
        """
        if (
                before.guild is None
                or before.author.bot
                or before.guild.id != Guilds.DDNET
        ):
            return

        addr = extract_address(after.content)
        if not addr:
            return

        msg = self.bot.get_message(self.message_cache.get(before.id))

        # If after.content contains a DDNet server
        # and after(message) is in a report ticket
        # and Moderators haven't been notified yet
        # -> delete the message
        # This is necessary because editing the message with an @mention does not actually notify the role/user...

        if (
                before.channel.name.startswith("report-")
                and before.channel not in self.mod_call
                and msg
        ):
            await msg.delete()
            msg = None

        embed, view, network = await self.discord_resp(addr, before.channel)

        if (
                after.channel.name.startswith("report-")
                and network == "DDraceNetwork"
                and after.channel not in self.mod_call
        ):
            self.mod_call.append(after.channel)
            msg = await after.channel.send(content=f"<@&{Roles.MODERATOR}>", embed=embed, view=view)
            self.message_cache[after.id] = msg.id
            return

        # This will send a new message with an @Moderator ping if msg is None
        if (
                before.channel.name.startswith("report-")
                and not msg
        ):
            try:
                if before.channel.topic.startswith("Ticket"):
                    msg = await before.channel.send(embed=embed, view=view)
            except AttributeError:  # NoneType case
                msg = await before.channel.send(embed=embed, view=view)
            self.message_cache[after.id] = msg.id
            return
        try:
            if isinstance(embed, discord.Embed):
                msg = self.bot.get_message(self.message_cache.get(before.id))
                msg = await msg.edit(embed=embed, view=view)
        except AttributeError:
            msg = await before.channel.send(embed=embed, view=view)

        self.message_cache[after.id] = msg.id

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Sends a notification whenever a staff member leaves the discord server"""
        if (
                member.guild.id != Guilds.DDNET
                or member.bot
                or not is_staff(member)
        ):
            return

        channel = self.bot.get_channel(Channels.MOD_C)
        await channel.send(f"A staff member named {member.name} ({member.display_name}) has left the server.")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if (
                not message.guild
                or message.author.bot
                or is_staff(message.author)
                or message.edited_at is not None
                or message.author in message.mentions
        ):
            return

        try:
            async for entry in message.guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                if (
                        entry.target.id == message.author.id
                        and (datetime.datetime.now(datetime.timezone.utc) - entry.created_at) < datetime.timedelta(
                    seconds=5)
                ):
                    if entry.user.bot or entry.user != message.author:
                        return
                    break
        except discord.Forbidden:
            return

        if message.mentions or message.role_mentions:
            user_mentions = [user for user in message.mentions if user.id != message.author.id and not user.bot]
            role_mentions = [role for role in message.role_mentions if role not in message.author.roles]
            if not user_mentions and not role_mentions:
                return

            now = datetime.datetime.now(datetime.timezone.utc)
            message_age = now - message.created_at

            if message_age > self.timeout:
                return

            mention_names = [f"<@{user.id}>" for user in user_mentions]
            mention_names.extend(f"<@&{role.id}>" for role in role_mentions)

            embed = discord.Embed(
                title="Ghost ping detected!",
                color=discord.Color.dark_grey(),
                timestamp=now
            )
            embed.add_field(name="Message Author", value=message.author.mention, inline=True)
            embed.add_field(name="Message Content", value=message.content or "*No content*", inline=True)

            with contextlib.suppress(discord.Forbidden):
                await message.channel.send(embed=embed)
                await message.author.timeout(now + datetime.timedelta(minutes=2), reason="Ghost pinging")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        message_age = now - before.created_at
        if message_age > self.timeout:
            return

        if before.author in before.mentions:
            return

        # users
        before_mentions = {user.id for user in before.mentions}
        after_mentions = {user.id for user in after.mentions}
        removed_mentions = before_mentions - after_mentions
        removed_mentions -= {before.author.id}
        removed_mentions = {uid for uid in removed_mentions if not before.guild.get_member(uid).bot}
        # roles
        before_roles = {role.id for role in before.role_mentions}
        after_roles = {role.id for role in after.role_mentions}
        removed_roles = before_roles - after_roles
        removed_roles -= {role.id for role in before.author.roles}

        if not (removed_mentions or removed_roles):
            if (before.mentions or before.role_mentions) and before.id not in self.edited_with_mentions:
                self.edited_with_mentions.add(before.id)
            return

        if before.id in self.edited_with_mentions:
            return

        self.edited_with_mentions.add(before.id)

        mention_names = [f"<@{user_id}>" for user_id in removed_mentions]
        mention_names.extend(f"<@&{role_id}>" for role_id in removed_roles)

        embed = discord.Embed(
            title="Ghost ping detected! (edit)",
            color=discord.Color.light_embed(),
            timestamp=now
        )
        embed.add_field(name="Message Author", value=before.author.mention, inline=True)
        embed.add_field(name="Original Message", value=before.content or "*No content*", inline=True)
        await after.reply(embed=embed, mention_author=False)

        with contextlib.suppress(discord.Forbidden):
            await before.author.timeout(now + datetime.timedelta(minutes=1), reason="Ghost pinging (edit)")

    # TODO: Include UPLOADED attachments
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        now = time.time()
        signature = (message.content,)

        self.user_messages[message.author.id] = [
            (sig, msg, t) for (sig, msg, t) in self.user_messages.get(message.author.id, [])
            if now - t <= 20
        ]
        self.user_messages[message.author.id].append((signature, message, now))

        channels = {msg.channel.id for (sig, msg, t) in self.user_messages[message.author.id] if sig == signature}

        if len(channels) >= 4 and signature not in self.alerted[message.author.id]:
            # try:
            #     until = datetime.timedelta(hours=1)
            #     await message.author.timeout(
            #         until, reason="Spamming identical messages in multiple channels"
            #     )
            action = "User has been timed out for 1 hour."
            # except Exception as e:
            #     action = f"Failed to timeout user: {e}"

            for sig, msg, t in self.user_messages[message.author.id]:
                if sig == signature:
                    try:
                        await msg.delete()
                    except Exception as e:
                        print(f"Failed to delete message {msg.id}: {e}")

            self.alerted[message.author.id].add(signature)
            mod_channel = self.bot.get_channel(Channels.MODERATOR)
            await mod_channel.send(
                f"⚠️ <@&{Roles.DISCORD_MODERATOR}> User {message.author.mention} sent the same message "
                f"in {len(channels)} channels:\n"
                f"{action}"
            )


# TODO: Add changelogs for every command.
class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = ModeratorDB(bot)
        self.actions: dict[int | str, tuple[discord.User, str, str]] = {}

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
        await ctx.defer(ephemeral=True)

        if member.timed_out_until and member.timed_out_until > datetime.datetime.now(datetime.timezone.utc):
            await ctx.send(
                f"{member.mention} is already timed out. "
                f"Will be cleared in <t:{int(member.timed_out_until.timestamp())}:R>."
            )
            return

        self.actions[member.id] = (ctx.author, "timeout", reason)
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

        self.actions[member.id] = (ctx.author, "kick", reason)
        await ctx.guild.ban(member, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.guild.unban(member)
        await ctx.send(f"User {member.mention} has been kicked. Reason: {reason}")

    @kick_group.command(
        name="id",
        with_app_command=True,
        description="Kicks a user by their ID.")
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        id="The users ID to kick.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for the kick.")
    async def kick_user_id(
            self, ctx, id: str, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        await ctx.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(id))
        member = ctx.guild.get_member(user.id)
        if member is None:
            await ctx.send(f"User with ID: `{id}` is not in the server.")
            return

        # Using guild.ban allows to mass delete messages from a user. The user is unbanned right after.
        self.actions[member.id] = (ctx.author, "kick", reason)
        await ctx.guild.ban(user, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.guild.unban(user)
        await ctx.send(f"User {user.mention} (ID: `{id}`) has been kicked. Reason: {reason}")

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
            await ctx.send("I do not have permission to view bans.")
            return
        except discord.HTTPException:
            await ctx.send("HTTPException: Failed to check if user is banned. Try again later.")
            return

        self.actions[user.id] = (ctx.author, "ban", reason)
        await ctx.guild.ban(user, delete_message_seconds=seconds_list[delete_message_history.value], reason=reason)
        await ctx.send(f"User {user.mention} has been banned for \"{reason}\"")

    @ban_group.command(name="id", with_app_command=True, description="Bans a user by their ID.")
    @commands.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.checks.has_any_role(Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR)
    @app_commands.choices(delete_message_history=history())
    @app_commands.describe(
        id="The user's ID to ban.",
        delete_message_history="How much of their recent message history to delete.",
        reason="The reason for banning")
    async def ban_user_id(
            self, ctx, id: str, delete_message_history: app_commands.Choice[int], *, reason: str
    ):
        await ctx.defer(ephemeral=True)

        try:
            user = await self.bot.fetch_user(int(id))
        except discord.NotFound:
            await ctx.send(f"Could not find user with ID: `{id}`.")
            return

        try:
            async for ban_entry in ctx.guild.bans():
                if ban_entry.user.id == user.id:
                    await ctx.send(f"{user.mention} (ID: `{id}`) is already banned.")
                    return
        except discord.Forbidden:
            await ctx.send("I do not have permission to view bans.")
            return
        except discord.HTTPException:
            await ctx.send("HTTPException: Failed to check if user is banned. Try again later.")
            return

        self.actions[user.id] = (ctx.author, "ban", reason)
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
    @app_commands.describe(id="The user ID to unban.")
    async def unban_user_id(self, ctx, id: str):
        await ctx.defer(ephemeral=True)
        user = await self.bot.fetch_user(int(id))

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
        info = await self.manager.fetch_user_info(user)

        if not info:
            await ctx.send(embed=NoMemberInfoEmbed())
            return

        em = [MemberInfoEmbed(info)]
        empty_sections = []
        non_empty_embeds = []

        if info.timeouts:
            non_empty_embeds.append(TimeoutsEmbed(info))
        else:
            empty_sections.append("Timeouts")

        if info.bans:
            non_empty_embeds.append(BansEmbed(info))
        else:
            empty_sections.append("Bans")

        if info.kicks:
            non_empty_embeds.append(KicksEmbed(info))
        else:
            empty_sections.append("Kicks")

        if empty_sections:
            em.append(NoEntries(empty_sections))

        # Add all non-empty embeds
        em.extend(non_empty_embeds)

        await ctx.send(embeds=em)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        guild = entry.guild

        if guild.id != Guilds.DDNET:
            return

        target = entry.target
        reason = entry.reason or "No reason provided"
        action = entry.action

        # bans
        if action == discord.AuditLogAction.ban:
            if target.id in self.actions:
                moderator, action_type, custom_reason = self.actions.pop(target.id)
                await self.manager.log_action(moderator, target, action_type, custom_reason)
            else:
                await self.manager.log_action(entry.user, target, "ban", reason)

        # kicks
        elif action == discord.AuditLogAction.kick:
            if target.id in self.actions:
                moderator, action_type, custom_reason = self.actions.pop(target.id)
                await self.manager.log_action(moderator, target, action_type, custom_reason)
            else:
                await self.manager.log_action(entry.user, target, "kick", reason)

        # timeouts
        elif action == discord.AuditLogAction.member_update:
            if not hasattr(entry.before, "timed_out_until"):
                return

            before = entry.before.timed_out_until
            after = entry.after.timed_out_until

            if before is None and after is not None:
                if target.id in self.actions:
                    moderator, action_type, custom_reason = self.actions.pop(target.id)
                    await self.manager.log_action(moderator, target, action_type, custom_reason)
                else:
                    await self.manager.log_action(entry.user, target, "timeout", reason)

    @commands.command()
    @commands.check(ddnet_only)
    @commands.has_permissions(administrator=True)
    async def import_bans(self, ctx):
        string = await self.manager.import_existing_bans(ctx.guild)
        await ctx.send(string)


class NoChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def robot_cmds(self, message: discord.Message):
        if (
                not message.author.bot
                and message.channel.id == Channels.BOT_CMDS
        ):
            with contextlib.suppress(discord.NotFound):
                await message.delete()

    @commands.Cog.listener("on_message")
    async def playerfinder(self, message: discord.Message):
        if (
                message.channel.id == Channels.PLAYERFINDER
                and message.author != self.bot.user
        ):
            with contextlib.suppress(discord.NotFound):
                await message.delete()

    @commands.Cog.listener("on_message")
    async def media_only(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id == Channels.MEDIA_ONLY:
            has_attachment = bool(message.attachments)
            has_media_embed = any(embed.type in ("image", "video") for embed in message.embeds)
            contains_url = bool(re.compile(r'https?://\S+').search(message.content))

            if not (has_attachment or has_media_embed or contains_url):
                try:
                    await message.delete()
                    try:
                        await message.author.send(
                            f"{message.channel.jump_url}: Only media or links are allowed in this channel.",
                            delete_after=30
                        )
                    except discord.Forbidden:
                        await message.channel.send(
                            f"{message.author.mention} Only media or links are allowed in this channel.",
                            delete_after=5
                        )
                except discord.Forbidden:
                    log.error("media_only: Missing permissions to delete messages.")
                return


async def setup(bot: commands.bot):
    await bot.add_cog(AutoMod(bot))
    await bot.add_cog(Moderation(bot))
    await bot.add_cog(NoChat(bot))
