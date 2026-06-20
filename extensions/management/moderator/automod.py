import re
import contextlib
import os
import time
from io import BytesIO
from collections import defaultdict

from requests_cache import CachedSession
import discord
from discord.ext import commands
import datetime

from constants import Guilds, Roles, Channels
from utils.conn import source
from utils.master_parser import MASTER_URL, parse_master
from utils.misc import flag, log_to
from .server_info import ServerInfoEmbed, ServerLinksView
from .views.containers.notices import GhostPingView, SpamAlertView

from utils.text import extract_address
from utils.checks import is_staff

# If the bot is running into KeyErrors, clear the sqlite cache via the admin hub's "Clear Cache" button.
os.makedirs("data/cache", exist_ok=True)
session = CachedSession(cache_name="data/cache/http_cache", expire_after=60 * 60 * 2)

SPAM_IMAGE_FORMATS = (".webp", ".jpeg", ".jpg", ".png", ".gif")
SPAM_IMAGE_MAX = 8 * 1024 * 1024


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


def fetch_live_stats(addr):
    """Live stats for `addr` from the master server list: player count and
    current map.

    info.ddnet.org/info has none of this, so this reads the master list. It
    uses a short cache (the shared session's 2h TTL would make these
    meaningless); values can be up to ~60s old. Returns a dict with keys
    players / max_players / map (max_players or map may be None), or None when
    the server isn't in the list (offline/unregistered).
    """
    try:
        raw = session.get(MASTER_URL, expire_after=60).json()
    except Exception:
        return None

    for server in parse_master(raw).servers:
        if server.normalized_address == addr:
            info = server.info
            return {
                "players": info.total_players,
                "max_players": info.max_players or info.max_clients,
                "map": info.map.name if info.map else None,
            }
    return None


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
        Look up the server address and prepare the response: an (embed, view,
        network) tuple. `view` is the join/contact button view (or None when
        there's no button to show); `network` lets the caller decide whether to
        ping moderators after seeing it.
        """
        info = fetch_server_info(addr)

        if not info:
            return ServerInfoEmbed.from_server_info(None), None, None

        # Live data (player count + current map) comes from the master list,
        # not info.ddnet.org/info.
        stats = fetch_live_stats(addr)
        if stats:
            info.update(stats)

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
        is_ticket = self.bot.ticket_manager.tickets.get(channel.id) is not None
        network = info.get("network")

        embed = ServerInfoEmbed.from_server_info(info, ticket=is_ticket, region=region, addr=addr)
        view = ServerLinksView(
            addr,
            network=network,
            is_ddnet=(network == "DDraceNetwork"),
            ticket=is_ticket,
            contact_url=contact_url,
        )
        return embed, (view if view.children else None), network

    @staticmethod
    async def _reply(message: discord.Message, embed, view, *, ping_mods: bool = False):
        """Reply to `message` with the server-info embed (and button view),
        without pinging the message author. `ping_mods` adds the @Moderator
        role ping in the message content (report channels). Falls back to a
        plain channel message if the original was deleted before we replied."""
        allowed = discord.AllowedMentions(
            everyone=False, users=False, roles=ping_mods, replied_user=False
        )
        kwargs = {"embed": embed, "allowed_mentions": allowed}
        if ping_mods:
            kwargs["content"] = f"<@&{Roles.MODERATOR}>"
        if view is not None:
            kwargs["view"] = view
        try:
            return await message.reply(**kwargs)
        except discord.HTTPException:
            return await message.channel.send(**kwargs)

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

        embed = None
        view = None
        network = None
        with contextlib.suppress(discord.Forbidden):
            embed, view, network = await self.discord_resp(addr, message.channel)
        if embed is None:
            return

        if (
                message.channel.name.startswith("report-")
                and network == "DDraceNetwork"
                and message.channel not in self.mod_call
        ):
            self.mod_call.append(message.channel)
            msg = await self._reply(message, embed, view, ping_mods=True)
            self.message_cache[message.id] = msg.id
            return

        msg = await self._reply(message, embed, view)
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
            msg = await self._reply(after, embed, view, ping_mods=True)
            self.message_cache[after.id] = msg.id
            return

        # This will send a new message if msg is None
        if (
                before.channel.name.startswith("report-")
                and not msg
        ):
            try:
                if before.channel.topic.startswith("Ticket"):
                    msg = await self._reply(after, embed, view)
            except AttributeError:  # NoneType case
                msg = await self._reply(after, embed, view)
            if msg:
                self.message_cache[after.id] = msg.id
            return

        try:
            msg = self.bot.get_message(self.message_cache.get(before.id))
            msg = await msg.edit(embed=embed, view=view)
        except AttributeError:
            msg = await self._reply(after, embed, view)
        except discord.HTTPException:
            # The cached message is a Components V2 message (from the container
            # era) and can't be edited into an embed message, so replace it.
            msg = await self._reply(after, embed, view)

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

            with contextlib.suppress(discord.Forbidden):
                await message.channel.send(
                    view=GhostPingView(message.author, message.content),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
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

        await after.reply(
            view=GhostPingView(before.author, before.content, edited=True),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        with contextlib.suppress(discord.Forbidden):
            await before.author.timeout(now + datetime.timedelta(minutes=1), reason="Ghost pinging (edit)")

    @staticmethod
    def spam_signatures(message: discord.Message) -> set[str]:
        """Just a test"""
        signatures = set()
        if text := message.content.strip().casefold():
            signatures.add(f"t:{text}")
        for attachment in message.attachments:
            if attachment.width and attachment.height:
                signatures.add(
                    f"a:{attachment.size}:{attachment.width}x{attachment.height}:{attachment.content_type}"
                )
            else:
                signatures.add(f"a:{attachment.filename.lower()}:{attachment.size}")
        for embed in message.embeds:
            for media in (embed.thumbnail, embed.image):
                if media and media.url:
                    signatures.add(f"e:{media.url}")
        return signatures

    @staticmethod
    def spam_summary(message: discord.Message) -> str:
        """Human-readable description of what was spammed, for the mod alert."""
        if text := message.content.strip():
            return text
        if message.attachments:
            return "[attachments] " + ", ".join(
                f"{a.filename} ({a.size} bytes)" for a in message.attachments
            )
        if message.embeds:
            return "[embedded media]"
        return "[no text]"

    @staticmethod
    async def capture_images(message: discord.Message) -> list[discord.File]:
        files: list[discord.File] = []
        for attachment in message.attachments:
            if not attachment.filename.lower().endswith(SPAM_IMAGE_FORMATS):
                continue
            if attachment.size > SPAM_IMAGE_MAX:
                continue
            try:
                data = await attachment.read()
            except discord.HTTPException:
                continue
            ext = os.path.splitext(attachment.filename)[1] or ".png"
            files.append(discord.File(BytesIO(data), filename=f"spam_{len(files)}{ext}"))
        return files

    @commands.Cog.listener('on_message')
    async def spam_protection(self, message: discord.Message):
        if not message.guild or message.author.bot or message.guild.id != Guilds.DDNET:
            return

        signatures = self.spam_signatures(message)
        if not signatures:
            return

        now = time.time()
        messages = [
            (msg, sigs, t)
            for msg, sigs, t in self.user_messages.get(message.author.id, [])
            if now - t <= 20
        ]
        messages.append((message, signatures, now))
        self.user_messages[message.author.id] = messages

        triggered = None
        spammed_channels = set()
        for signature in signatures:
            channels = {msg.channel.id for msg, sigs, _ in messages if signature in sigs}
            if len(channels) >= 4:
                triggered = signature
                spammed_channels = channels
                break

        if triggered and triggered not in self.alerted[message.author.id]:
            try:
                await message.author.timeout(
                    datetime.timedelta(hours=1),
                    reason="Spamming identical messages/images in multiple channels",
                )
                action = "User timed out successfully."
            except Exception as e:
                action = f"Failed to timeout user: {e}"

            files = await self.capture_images(message)

            for msg, sigs, _ in messages:
                if triggered in sigs:
                    with contextlib.suppress(Exception):
                        await msg.delete()
            self.alerted[message.author.id].add(triggered)

            await log_to(
                self.bot, Channels.LOG_MOD_ALERTS,
                view=SpamAlertView(
                    Roles.DISCORD_MODERATOR, message.author, spammed_channels,
                    self.spam_summary(message), action, files=files,
                ),
                files=files,
            )
