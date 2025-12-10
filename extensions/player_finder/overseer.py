import asyncio
import contextlib
import logging
import os
import re
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

from .manager import Player
from constants import Guilds, Channels, Roles
from utils.master_parser import Server, Client, fetch_master_list, find_servers_by_community
from utils.text import choice_to_datetime, to_discord_timestamp
from utils.checks import is_staff
from utils.misc import duration, name_filter
from .utils import filter, players, group_players_by_server
from .layoutview import PlayerfinderView

log = logging.getLogger()

BAN_RE = (
    r"(?P<author>\w+) banned (?P<banned_user>.+?) `(?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})` "
    r"for `(?P<reason>.+?)` until (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)

UNBAN_RE = (
    r"^Unbanned (?P<name>.+)$"
)


def predicate(interaction: discord.Interaction) -> bool:
    return interaction.channel.id == Channels.PLAYERFINDER and is_staff(
        interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
    )


class Overseer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.master_url = "https://master1.ddnet.org/ddnet/15/servers.json"
        self.info_url = "https://info.ddnet.org/info"
        self.manager = bot.pfm
        self.overseer.start()
        self.players_online: dict[str, list[tuple[Server, Client]]] = {}
        self.ddnet_servers_addresses = []

        # new: multi-message tracking
        self.page_cache: dict[int, str] = {}
        self.playerfinder_messages: list[discord.Message] = []

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self) -> None:
        self.overseer.cancel()
        await self.clean_up()
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def clean_up(self) -> None:
        channel = self.bot.get_channel(Channels.PLAYERFINDER)
        await channel.purge()
        self.playerfinder_messages.clear()
        self.page_cache.clear()

    async def get_master_data(self):
        try:
            if self.session is None:
                log.warning("Playerfinder: session not initialized yet")
                return
            master = await fetch_master_list(self.session)
        except Exception as e:
            log.warning("Playerfinder fetch failed: %r", e)
            return

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

    async def del_expired_bans(self):
        now = datetime.now().replace(tzinfo=None)
        expired = [p for p in self.manager.players if p.expiry_date < now]
        for player in expired:
            await self.manager.del_player(player)

    @tasks.loop(seconds=10)
    async def overseer(self):
        await self.del_expired_bans()
        await self.get_master_data()

        copycat_cog = self.bot.get_cog("Copycat")
        if copycat_cog is not None:
            await copycat_cog.detect_copycats()

        await self.playerfinder()

    @overseer.before_loop
    async def before_overseer(self):
        await self.bot.wait_until_ready()
        pf_channel = self.bot.get_channel(Channels.PLAYERFINDER)
        await pf_channel.purge()
        self.playerfinder_messages.clear()
        self.page_cache.clear()
        await self.manager.load_players()

    async def playerfinder(self):
        pages = self.build_pages()
        channel = self.bot.get_channel(Channels.PLAYERFINDER)

        # NEW: fetch current copycat summary text
        copycat_cog = self.bot.get_cog("Copycat")
        if copycat_cog is not None and hasattr(copycat_cog, "build_summary"):
            copycat_summary = copycat_cog.build_summary()
        else:
            copycat_summary = "*Copycat detection unavailable.*"

        desired_count = len(pages)
        current_count = len(self.playerfinder_messages)

        if current_count > desired_count:
            for msg in self.playerfinder_messages[desired_count:]:
                with contextlib.suppress(discord.NotFound, discord.HTTPException):
                    await msg.delete()
            del self.playerfinder_messages[desired_count:]
            self.page_cache.clear()

        for index in range(min(current_count, desired_count)):
            msg = self.playerfinder_messages[index]
            page_content = pages[index]

            if self.page_cache.get(index) == page_content:
                # content for first TextDisplay is unchanged; still update the copycat panel
                view = PlayerfinderView()
                view.container.children[0].content = page_content
                view.container.children[2].content = copycat_summary
                try:
                    await msg.edit(view=view)
                except discord.NotFound:
                    sent = await channel.send(view=view)
                    self.playerfinder_messages[index] = sent
                continue

            view = PlayerfinderView()
            view.container.children[0].content = page_content
            view.container.children[2].content = copycat_summary

            try:
                await msg.edit(view=view)
            except discord.NotFound:
                sent = await channel.send(view=view)
                self.playerfinder_messages[index] = sent
            finally:
                self.page_cache[index] = page_content

        for index in range(current_count, desired_count):
            page_content = pages[index]
            view = PlayerfinderView()
            view.container.children[0].content = page_content
            view.container.children[2].content = copycat_summary

            sent = await channel.send(view=view)
            self.playerfinder_messages.append(sent)
            self.page_cache[index] = page_content

    def author_label(self, player: "Player") -> str:
        # I tried muting @mentions, but doesn't seem to work with ui.containers yet
        # I might change this once ui.containers work with AllowedMentions
        guild = self.bot.get_guild(Guilds.DDNET)
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
        reason = player.reason.replace("\n", " ").strip()

        links: list[str] = []
        for i, (server, _cli) in enumerate(entries, start=1):
            if len(links) >= max_links:
                break
            if addr := server.normalized_address or "":
                links.append(f"[[{i}]](https://ddnet.org/connect-to/?addr={addr})")

        servers_str = " ".join(links) if links else ""

        return (
            f"**{player.name}**"
            f"{(f': [{reason}]({player.ban_link})' if player.ban_link else '')} "
            f"| Exp: {ts} "
            f"| By: {by} "
            f"| {servers_str}"
        )

    def build_pages(self) -> list[str]:
        """
        Build paginated text content from self.manager.players + self.players_online.

        Returns:
            List of page strings to be used as TextDisplay content.
        """
        tracked = [p for p in self.manager.players if not name_filter(p.name)]
        online = [
            (p.name, p, self.players_online[p.name])
            for p in tracked
            if p.name in self.players_online
        ]

        if not online:
            return ["*No tracked players online.*"]

        pages: list[str] = []
        lines_per_page = 8

        for start in range(0, len(online), lines_per_page):
            page = online[start:start + lines_per_page]

            lines = [
                self.format_player_line(player, entries)
                for name, player, entries in page
            ]
            header = "" if pages else "# **Playerfinder**\n"
            page_content = header + "\n".join(lines)
            pages.append(page_content)

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

    pf = app_commands.Group(
        name="pf",
        description="Playerfinder watchlist commands",
        guild_ids=[Guilds.DDNET],
        guild_only=True
    )

    @pf.command(name="list", description="Uploads a text file containing all players currently in the watchlist")
    @app_commands.check(predicate)
    async def pf_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self.manager.players:
            await interaction.followup.send("No players found.")
        else:
            response = "Current List:\n"
            for player in self.manager.players:
                response += (
                    f'"{player.name}": '
                    f"Added by {player.added_by} "
                    f'for reason: "{player.reason}", '
                    f"expires: {player.expiry_date}\n"
                )
            with open("data/player_list.txt", "w", encoding="utf-8") as f:
                f.write(response)
            with open("data/player_list.txt", "rb") as f:
                await interaction.followup.send(file=discord.File(f, "player_list.txt"))
            os.remove("data/player_list.txt")

    @pf.command(name="add", description="Adds a player to the watchlist.")
    @app_commands.check(predicate)
    @app_commands.describe(name="Name of the player", reason="Reason", expiry_date="Duration")
    @app_commands.choices(expiry_date=duration())
    async def pf_add(self, interaction: discord.Interaction, name: str, reason: str, expiry_date: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            expiry_datetime = choice_to_datetime(expiry_date)
            player = await self.manager.add_player(
                name=name,
                reason=reason,
                added_by=interaction.user,
                expiry_date=expiry_datetime,
            )
        except ValueError as e:
            await interaction.followup.send(str(e))
            return
        try:
            await interaction.followup.send(
                f"Added: `{player.name}` "
                f"for reason: `{player.reason}`, "
                f"expires: `{player.expiry_date.strftime('%Y-%m-%d %H:%M:%S')}`"
            )
        except discord.app_commands.errors.CommandInvokeError as e:
            await interaction.followup.send(str(e))

    @pf.command(name="rm", description="Removes a player from the watchlist.")
    @app_commands.check(predicate)
    @app_commands.describe(name="Name of the player")
    async def pf_rm(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            player_obj = self.manager.find_player(name)
            await self.manager.del_player(player_obj)
            await interaction.followup.send(f"Removed player: {player_obj.name}")
        except AttributeError:
            await interaction.followup.send(f'Player named "{name}" not found.')

    @pf.command(name="info", description="Sends playerfinder related info's of a player.")
    @app_commands.check(predicate)
    @app_commands.describe(name="Name of the player")
    async def pf_info(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if player_obj := self.manager.find_player(name):
            await interaction.followup.send(f"{player_obj}")
        else:
            await interaction.followup.send(
                f'Player named "{name}" not in watchlist.'
            )

    @pf.command(name="edit", description="Edits the info field of the provided player.")
    @app_commands.check(predicate)
    @app_commands.describe(name="Name of the player", reason="The new reason")
    async def pf_edit(self, interaction: discord.Interaction, name: str, reason: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            old_reason, player = await self.manager.edit_reason(name, reason)
            await interaction.followup.send(
                f"Info for {player.name} has been changed:\n"
                "```diff\n"
                f"+{player.reason}\n"
                f"-{old_reason}\n"
                "```"
            )
        except ValueError:
            await interaction.followup.send(
                f'Player named "{name}" not in watchlist.'
            )

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(
        name="stop_search",
        description="Stops the player finder task.")
    async def stop_player_search(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if not self.overseer.is_running():
            await interaction.followup.send(
                "The player search process is not currently running."
            )
        else:
            self.overseer.cancel()
            await self.clean_up()
            await interaction.followup.send("Process stopped.")

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="start_search", description="Starts the player finder task.")
    async def start_player_search(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if self.overseer.is_running():
            await interaction.followup.send(
                "The player search process is already running."
            )
        else:
            await self.clean_up()
            self.overseer.start()
            await interaction.followup.send("Initializing search...")

    @staticmethod
    @start_player_search.error
    @stop_player_search.error
    @pf.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        async def send(content: str):
            if interaction.response.is_done():  # noqa
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)  # noqa

        if isinstance(error, app_commands.CheckFailure):
            await send(
                "You are not allowed to use that command here. Try again in the channel associated with the app command."
            )
            interaction.extras["error_handled"] = True
            return


class PlayerFinder(Overseer):
    @app_commands.command(
        name="find", description="Search for a player currently in-game")
    @app_commands.describe(name="The players name you're looking for.")
    async def search_player(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        players_dict = await players(self.bot.session, self.master_url)
        if name in players_dict:
            player_info = players_dict[name]
            message = (
                f'Found {len(player_info)} server(s) with "{name}" currently playing:\n'
            )
            for i, server in enumerate(player_info, 1):
                server_name, server_address = server
                message += f"{i}. Server: {server_name} — Link: <https://ddnet.org/connect-to/?addr={server_address}/>\n"

            if len(message) > 2000:
                message = "The message is too long. Please avoid using common names when using this function."
            await interaction.followup.send(message)
        else:
            await interaction.followup.send(f'There is currently no player online with name "{name}"')

        if interaction.response.is_done():  # noqa
            return

    @staticmethod
    @search_player.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        async def send(content: str):
            if interaction.response.is_done():  # noqa
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)  # noqa

        if isinstance(error, app_commands.CheckFailure):
            await send(
                "You are not allowed to use that command here. Try again in the channel associated with the app command."
            )
            interaction.extras["error_handled"] = True
            return


async def setup(bot):
    await bot.add_cog(PlayerFinder(bot))
