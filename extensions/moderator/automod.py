import re
import contextlib
import time
from collections import defaultdict

from requests_cache import CachedSession
import discord
from discord.ext import commands
import datetime

from constants import Guilds, Roles, Channels
from utils.conn import source
from utils.misc import flag
from .views.links import ButtonLinks
from .embeds import ServerInfoEmbed

from utils.text import extract_address
from utils.checks import is_staff

# If the bot is running into KeyErrors, use /clear_cache to clear the sqlite cache the bot uses.
session = CachedSession(cache_name="data/cache", expire_after=60 * 60 * 2)


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

    resp = source("https://info.ddnet.org/info", session=session)
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
    async def verify_address(self, message: discord.Message):
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
    async def verify_address_edit(self, before: discord.Message, after: discord.Message):
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

    @commands.Cog.listener('on_member_remove')
    async def staff_rq(self, member: discord.Member):
        """Sends a notification whenever a staff member leaves the discord server"""
        if (
                member.guild.id != Guilds.DDNET
                or member.bot
                or not is_staff(member)  # noqa
        ):
            return

        channel = self.bot.get_channel(Channels.MOD_C)
        await channel.send(f"A staff member named {member.name} ({member.display_name}) has left the server.")

    @commands.Cog.listener('on_message_delete')
    async def ghost_pings(self, message: discord.Message):
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

    @commands.Cog.listener('on_message_edit')
    async def ghost_ping_edit(self, before: discord.Message, after: discord.Message):
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
    @commands.Cog.listener('on_message')
    async def spam_protection(self, message: discord.Message):
        if message.author.bot or message.guild.id != Guilds.DDNET:
            return

        now = time.time()
        content = message.content

        messages = self.user_messages.get(message.author.id, [])
        messages = [(msg, t) for msg, t in messages if now - t <= 20]
        messages.append((message, now))
        self.user_messages[message.author.id] = messages

        channels = {msg.channel.id for msg, _ in messages if msg.content == content}

        if len(channels) >= 4 and content not in self.alerted[message.author.id]:
            try:
                await message.author.timeout(
                    datetime.timedelta(hours=1),
                    reason="Spamming identical messages in multiple channels",
                )
                action = "User timed out successfully."
            except Exception as e:
                action = f"Failed to timeout user: {e}"

            for msg, _ in messages:
                if msg.content == content:
                    try:
                        await msg.delete()
                    except Exception as e:
                        print(f"Failed to delete message {msg.id}: {e}")

            self.alerted[message.author.id].add(content)

            embed = discord.Embed(
                title="Spam Alert",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
            embed.add_field(name="Channels", value=", ".join(f"<#{cid}>" for cid in channels), inline=False)
            embed.add_field(name="Message Content", value=content[:1024], inline=False)
            embed.add_field(name="Action Taken", value=action, inline=False)

            log_channel = self.bot.get_channel(Channels.LOGS)
            await log_channel.send(f"<@&{Roles.DISCORD_MODERATOR}>", embed=embed)
