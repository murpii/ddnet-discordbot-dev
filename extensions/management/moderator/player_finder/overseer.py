import contextlib
import logging
import re
from datetime import datetime
import discord
from discord.ext import commands, tasks

from .manager import Player
from constants import Channels
from utils.master_parser import Server, Client, fetch_master_list, find_servers_by_community
from utils.text import to_discord_timestamp, inline_code, escape_link_label
from utils.misc import connect_url, name_filter
from .layoutview import PlayerfinderView, CustomView

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

BAN_RE = (
    r"(?P<author>\w+) banned (?P<banned_user>.+?) `(?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})` "
    r"for `(?P<reason>.+?)` until (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)

UNBAN_RE = (
    r"^Unbanned (?P<name>.+)$"
)


class Overseer(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None
        self.master_url = "https://master1.ddnet.org/ddnet/15/servers.json"
        self.info_url = "https://info.ddnet.org/info"
        self.manager = bot.pfm
        self.overseer.start()
        self.players_online: dict[str, list[tuple[Server, Client]]] = {}
        self.ddnet_servers_addresses = []
        self.channel: discord.TextChannel = self.bot.get_channel(Channels.PLAYERFINDER)
        self.messages: list[discord.Message] = []
        self.message_keys: list[str] = []

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self) -> None:
        self.overseer.cancel()
        await self.clean_up()
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def clean_up(self) -> None:
        self.messages.clear()
        self.message_keys.clear()
        self.players_online.clear()
        self.ddnet_servers_addresses.clear()
        self.manager.players.clear()
        await self.channel.purge()

    async def get_master_data(self) -> list[Server] | None:
        try:
            if self.session is None:
                log.warning("Playerfinder: session not initialized yet")
                return None
            master = await fetch_master_list(self.session)
        except Exception as e:
            log.warning("Playerfinder fetch failed: %r", e)
            return None

        ALLOWED_GAMEMODES = {
            "DDraceNetwork", "Test", "Tutorial",
            "Block", "Infection", "iCTF",
            "gCTF", "Vanilla", "zCatch",
            "TeeWare", "TeeSmash", "Foot",
            "xPanic", "Monster",
        }

        ddnet_servers = [
            s for s in find_servers_by_community(master, "ddnet")
            if s.info.game_type in ALLOWED_GAMEMODES
        ]

        for server in ddnet_servers:
            self.ddnet_servers_addresses.append(server.normalized_address)

        new_players: dict[str, list[tuple[Server, Client]]] = {}

        for server in ddnet_servers:
            for client in server.info.clients:
                new_players.setdefault(client.name, []).append((server, client))

        self.players_online = new_players
        return ddnet_servers

    async def del_expired_bans(self):
        now = datetime.now().replace(tzinfo=None)
        expired = [p for p in self.manager.players if p.expiry_date < now]
        for player in expired:
            await self.manager.del_player(player)

    @tasks.loop(seconds=10)
    async def overseer(self):
        await self.del_expired_bans()
        ddnet_servers = await self.get_master_data()

        copycat_cog = self.bot.get_cog("Copycat")
        if copycat_cog is not None and ddnet_servers is not None:
            await copycat_cog.detect_copycats(ddnet_servers)

        # sync_messages only touches the API for panels whose content
        # actually changed, so syncing every loop is cheap: usually 0-2
        # edits per 10s, well under Discord's 5 requests / 5s per channel
        # 
        # If this ever does trip a rate limit, it shows up in
        # logs/ratelimits.log with the responsible code path
        await self.playerfinder()

    @overseer.before_loop
    async def before_overseer(self):
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(Channels.PLAYERFINDER)
        await self.channel.purge()
        self.messages.clear()
        self.message_keys.clear()
        await self.manager.load_players()

    def get_extra_summary(self) -> str:
        copycat_cog = self.bot.get_cog("Copycat")
        if copycat_cog is None:
            return "*Detection unavailable.*"
        return getattr(copycat_cog, "latest_summary", "*Detection unavailable.*")

    def build_panels(self) -> list[tuple[discord.ui.LayoutView, str]]:
        """
        Build the full, ordered list of messages we want in the channel.
        """
        panels: list[tuple[discord.ui.LayoutView, str]] = []

        panels.extend(
            (PlayerfinderView(page_content=page_content), page_content)
            for page_content in self.build_pages()
        )
        copycat_summary = self.get_extra_summary()
        panels.append((CustomView(copycat_summary), copycat_summary))

        return panels

    async def sync_messages(self, panels: list[tuple[discord.ui.LayoutView, str]]) -> None:
        """Reconcile the channel with the desired panels, preserving order"""
        while len(self.messages) > len(panels):
            msg = self.messages.pop()
            self.message_keys.pop()
            with contextlib.suppress(discord.NotFound, discord.HTTPException):
                await msg.delete()

        # keep/edit leading messages until the first one we can't reuse in place
        # everything from that index onward is rebuilt so ordering is preserved
        rebuild_from = len(panels)
        for index in range(len(panels)):
            if index >= len(self.messages):
                rebuild_from = index
                break

            view, key = panels[index]
            if self.message_keys[index] == key:
                continue  # unchanged, no API call

            try:
                await self.messages[index].edit(view=view)
                self.message_keys[index] = key
            except discord.NotFound:
                rebuild_from = index
                break

        if rebuild_from == len(panels):
            return

        for msg in self.messages[rebuild_from:]:
            with contextlib.suppress(discord.NotFound, discord.HTTPException):
                await msg.delete()
        del self.messages[rebuild_from:]
        del self.message_keys[rebuild_from:]

        # resend the remaining panels in order, they land at the bottom.
        for view, key in panels[rebuild_from:]:
            self.messages.append(await self.channel.send(view=view))
            self.message_keys.append(key)

    async def playerfinder(self):
        await self.sync_messages(self.build_panels())

    def forget_messages(self, deleted_ids: set[int]) -> None:
        """
        Drop tracked messages that were deleted from the channel (i.e. removed by
        hand). Keeping self.messages accurate lets the next sync_messages rebuild
        the correct order.
        """
        kept_messages: list[discord.Message] = []
        kept_keys: list[str] = []
        for msg, key in zip(self.messages, self.message_keys):
            if msg.id in deleted_ids:
                continue
            kept_messages.append(msg)
            kept_keys.append(key)
        self.messages = kept_messages
        self.message_keys = kept_keys

    @commands.Cog.listener('on_raw_message_delete')
    async def panel_deleted(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.channel_id == Channels.PLAYERFINDER:
            self.forget_messages({payload.message_id})

    @commands.Cog.listener('on_raw_bulk_message_delete')
    async def panels_bulk_deleted(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.channel_id == Channels.PLAYERFINDER:
            self.forget_messages(set(payload.message_ids))

    def author_label(self, player: "Player") -> str:
        # I tried muting @mentions, but doesn't seem to work with ui.containers yet
        # I might change this once ui.containers work with AllowedMentions
        guild = self.channel.guild
        if isinstance(player.added_by, discord.Member):
            m = player.added_by
        else:
            m = guild.get_member_named(str(player.added_by)) if guild else None
        return m.name if m else str(player.added_by)

    def format_player_line(
            self,
            player: "Player",
            entries: list[tuple["Server", "Client"]],
            max_links: int = 3,
    ) -> str:
        ts = to_discord_timestamp(player.expiry_date, "R")
        by = self.author_label(player)
        reason = escape_link_label(player.reason.replace("\n", " ").strip())

        sorted_entries = sorted(entries, key=lambda e: e[0].normalized_address or "")

        links: list[str] = []
        for i, (server, _cli) in enumerate(sorted_entries, start=1):
            if len(links) >= max_links:
                break
            if addr := server.normalized_address or "":
                links.append(f"[[{i}]]({connect_url(addr)})")

        servers_str = " ".join(links) if links else ""

        return (
            f"{inline_code(player.name)}"
            f"{(f': [{reason}]({player.ban_link})' if player.ban_link else '')} "
            f"| Exp: {ts} "
            f"| By: {by} "
            f"| {servers_str}"
        )

    def build_pages(self) -> list[str]:
        tracked = [p for p in self.manager.players if not name_filter(p.name)]
        online = [
            (p.name, p, self.players_online[p.name])
            for p in tracked
            if p.name in self.players_online
        ]

        if not online:
            return ["*No tracked players online.*"]  # fallback text

        header = "# **Playerfinder**\n"
        pages: list[str] = []
        current: list[str] = []
        used = len(header)

        for _name, player, entries in online:
            line = self.format_player_line(player, entries)
            sep = 1 if current else 0
            if current and used + sep + len(line) > 3800:
                pages.append("\n".join(current))
                current = []
                used = 0
                sep = 0

            current.append(line)
            used += sep + len(line)

        if current:
            pages.append("\n".join(current))

        pages[0] = header + pages[0]  # only the first page gets the title
        return pages

    @commands.Cog.listener('on_message')
    async def bans_listener(self, message: discord.Message) -> None:
        if message.channel.id != Channels.BANS:
            return

        if regex := re.match(BAN_RE, message.content):
            author = message.guild.get_member_named(regex['author'])

            await self.manager.add_player(
                name=regex["banned_user"],
                expiry_date=datetime.strptime(regex["timestamp"], "%Y-%m-%d %H:%M:%S"),
                added_by=author if author is not None else regex['author'],
                reason=regex["reason"],
                link=message.jump_url
            )

        if regex := re.match(UNBAN_RE, message.content):
            await self.manager.del_player(regex["name"])
