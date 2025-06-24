import asyncio
import contextlib
import logging
import os
import re
from collections import defaultdict
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from constants import Guilds, Channels, Roles
from utils.text import choice_to_datetime
from .manager import Player

log = logging.getLogger()

BAN_RE = (
    r"(?P<author>\w+) banned (?P<banned_user>.+?) `(?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})` until "
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)
BAN_REF_RE = (
    r"!ban "
    r"(?P<IP>\d{1,3}(?:\.\d{1,3}){3}) *"
    r"(?P<name>'[^']*'|\"[^\"]*\"|[^'\"\s]+)? *"
    r"(?P<duration>\d+[a-zA-Z]{1,2}) *"
    r"(?P<reason>.+)"
)
UNBAN_RE = (
    r""
)


def is_staff(member: discord.Member) -> bool:
    return any(r.id in (Roles.ADMIN, Roles.MODERATOR) for r in member.roles)


def predicate(interaction: discord.Interaction) -> bool:
    return interaction.channel.id == Channels.PLAYERFINDER and is_staff(
        interaction.user
    )


def duration() -> list:
    return [
        app_commands.Choice(name="For 30 minutes", value=0),
        app_commands.Choice(name="For 1 hour", value=1),
        app_commands.Choice(name="For 6 Hours", value=2),
        app_commands.Choice(name="For 12 Hours", value=3),
        app_commands.Choice(name="For 24 Hours", value=4),
        app_commands.Choice(name="For 3 Days", value=5),
        app_commands.Choice(name="For 7 Days", value=6),
        app_commands.Choice(name="For 14 Days", value=7),
        app_commands.Choice(name="For 30 Days", value=8)
    ]


class PlayerFinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.master_url = "https://master1.ddnet.org/ddnet/15/servers.json"
        self.info_url = "https://info.ddnet.org/info"
        self.manager = bot.pfm
        self.embed_messages = {}
        self.overseer.start()
        self.cache = {}

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self) -> None:
        self.overseer.cancel()
        await self.clean_up()
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def clean_up(self) -> None:
        channel = self.bot.get_channel(Channels.PLAYERFINDER)
        await channel.purge()

    @commands.Cog.listener('on_message')
    async def bans_listener(self, message: discord.Message) -> None:
        if message.author == self.bot.user:
            return

        if message.channel.id != Channels.BANS:
            return

        regex = re.match(BAN_RE, message.content)
        if not regex:
            print("Not Found")
            return

        ref_message = await message.channel.fetch_message(message.reference.message_id)
        regex_ref = re.match(BAN_REF_RE, ref_message.content)

        player = await self.manager.add_player(
            name=regex["banned_user"],
            addr=regex["IP"],
            expiry_date=datetime.strptime(regex["timestamp"], "%Y-%m-%d %H:%M:%S"),
            added_by=regex["author"],
            reason=regex_ref["reason"],
        )
        print(player)

    async def filter(self) -> list:
        gamemodes = [
            "DDNet", "Test", "Tutorial",
            "Block", "Infection", "iCTF",
            "gCTF", "Vanilla", "zCatch",
            "TeeWare", "TeeSmash", "Foot",
            "xPanic", "Monster",
        ]
        resp = await self.session.get(self.info_url)
        data = await resp.json()
        servers = data.get("servers", [])
        ddnet_ips = []
        for entry in servers:
            sv_list = entry.get("servers")
            for mode in gamemodes:
                server_lists = sv_list.get(mode)
                if server_lists is not None:
                    ddnet_ips += server_lists
        return ddnet_ips

    @staticmethod
    def format_address(address):
        if address_match := re.match(r"tw-0.6\+udp://([\d.]+):(\d+)", address):
            ip, port = address_match.groups()
            return f"{ip}:{port}"
        return None

    async def players(self) -> dict:
        resp = await self.session.get(self.master_url)
        data = await resp.json()
        players = defaultdict(list)

        for server in data["servers"]:
            server_addresses = []
            for address in server["addresses"]:
                fmt_addr = self.format_address(address)
                if fmt_addr is not None:
                    server_addresses.append(fmt_addr)
            if "clients" in server["info"]:
                for player in server["info"]["clients"]:
                    for address in server_addresses:
                        players[player["name"]].append(
                            (server["info"]["name"], address)
                        )
        return players

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(
        name="pf_list",
        description="Uploads a text file containing all players currently in the watchlist")
    async def player_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

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
                await interaction.followup.send(
                    file=discord.File(f, "player_list.txt")  # noqa
                )  # noqa
            os.remove("data/player_list.txt")

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="pf_add", description="Adds a player to the watchlist.")
    @app_commands.describe(name="Name of the player", reason="Reason", expiry_date="Duration")
    @app_commands.choices(expiry_date=duration())  # Use the choices from the duration function
    async def add_player(
            self, 
            interaction: discord.Interaction, 
            name: str, 
            reason: str, 
            expiry_date: int, 
            addr: str = None
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            # Convert the expiry_date (integer choice) to a datetime using a helper function
            expiry_datetime = choice_to_datetime(expiry_date)
            player = await self.manager.add_player(
                name=name,
                addr=addr or None,
                reason=reason,
                added_by=interaction.user,
                expiry_date=expiry_datetime,
            )
        except ValueError as e:
            await interaction.followup.send(e)
            return

        try:
            await interaction.followup.send(
                f"Added: `{player.name}` "
                f"for reason: `{player.reason}`, "
                f"expires: `{player.expiry_date.strftime('%Y-%m-%d %H:%M:%S')}`"
            )
        except discord.app_commands.errors.CommandInvokeError as e:
            await interaction.followup.send(e)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="pf_rm", description="Removes a player from the watchlist.")
    @app_commands.describe(name="Name of the player")
    async def remove_player(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            player_obj = self.manager.find_player(name)
            await self.manager.del_player(player_obj)
            await interaction.followup.send(f"Removed player: {player_obj.name}")
        except AttributeError:
            await interaction.followup.send(f'Player named "{name}" not found.')

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(
        name="pf_info", description="Sends playerfinder related info's of a player.")
    @app_commands.describe(name="Name of the player")
    async def send_info(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if player_obj := self.manager.find_player(name):
            await interaction.followup.send(f"{player_obj}")
        else:
            await interaction.followup.send(
                f'Player named "{name}" not in watchlist.'
            )

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(
        name="pf_edit", description="Edits the info field of the provided player.")
    @app_commands.describe(name="Name of the player", reason="The new reason")
    async def edit_info(self, interaction: discord.Interaction, name: str, reason: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        try:
            old_reason, player = await self.manager.edit_reason(name, reason)
            await interaction.followup.send(
                f"Info for {player.name} has been changed: \n"
                f"```diff\n- {old_reason}\n+ {player.reason}```"
            )
        except ValueError:
            await interaction.followup.send(
                f'Player named "{name}" not in watchlist.'
            )

    @app_commands.command(
        name="find", description="Search for a player currently in-game")
    @app_commands.describe(name="The players name you're looking for.")
    async def search_player(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        players_dict = await self.players()
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

    @tasks.loop(seconds=60)
    async def overseer(self):
        await self.del_expired_bans()
        server_filter = await self.filter()
        players_online = await self.players()

        players_filtered = {
            player.name: (player, [server for server in players_online[player.name] if server[1] in server_filter])
            for player in self.manager.players
            if player.name in players_online and any(
                server[1] in server_filter for server in players_online[player.name])
        }
        
        await self.playerfinder(players_filtered)

    @overseer.before_loop
    async def before_overseer(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(Channels.PLAYERFINDER)
        await channel.purge()
        await self.manager.load_players()

    async def playerfinder(self, players_online: dict):
        online_players = set(players_online.keys())
        online_players_embeds = set(self.embed_messages.keys())
        gone_offline = online_players_embeds - online_players

        channel = self.bot.get_channel(Channels.PLAYERFINDER)
        for player_name in gone_offline:
            with contextlib.suppress(discord.NotFound):
                message_id = self.embed_messages.pop(player_name)
                with contextlib.suppress(discord.errors.DiscordServerError):
                    message = await channel.fetch_message(message_id)
                    await message.delete()
        changes = {
            name: (player, servers)
            for name, (player, servers) in players_online.items()
            if name not in self.cache or self.cache[name] != (player, servers)
        }

        for name, (player, servers) in changes.items():
            embed = self.embed_struct(player, servers)
            await self.send_or_edit(name, embed)
            # Rate limit issues
            await asyncio.sleep(2)

        self.cache = players_online.copy()

    async def del_expired_bans(self):
        now = datetime.now().replace(tzinfo=None)
        for player in self.manager.players:
            if player.expiry_date < now:
                await self.manager.del_player(player)

    async def send_or_edit(self, player_name, embed):
        channel = self.bot.get_channel(Channels.PLAYERFINDER)
        excl_common_names_set = {
                                    "nameless tee", "brainless tee", "nameless", "dummy"
                                } | {
                                    f"({i})nameless tee" for i in range(1, 30)
                                } | {
                                    f"({i})brainless tee" for i in range(1, 30)
                                }
        
        if len(player_name) < 4 or player_name in excl_common_names_set:
            return

        try:
            if player_name in self.embed_messages:
                message_id = self.embed_messages[player_name]
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            else:
                print("cba")
                message = await channel.send(embed=embed)
                self.embed_messages[player_name] = message.id
        except discord.NotFound:
            print("abc")
            message = await channel.send(embed=embed)
            self.embed_messages[player_name] = message.id

    @staticmethod
    def embed_struct(player: Player, servers) -> discord.Embed:
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.title = f"Player: {player.name}"
        embed.description = (
            f"Reason: {player.reason}\n"
            f"Expires: `{player.expiry_date.strftime('%Y-%m-%d %H:%M:%S')}`\n"
        )
        for server_name, address in servers[:3]:
            data = (
                f"* Server: {server_name}\n"
                f" * <https://ddnet.org/connect-to/?addr={address}/>\n"
            )
            embed.add_field(
                name="",
                value=data,
                inline=False,
            )
        return embed

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

    @player_list.error
    @start_player_search.error
    @stop_player_search.error
    @search_player.error
    @remove_player.error
    @add_player.error
    @send_info.error
    @edit_info.error
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        async def send(content: str):
            if interaction.response.is_done():  # noqa
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)  # noqa

        if isinstance(error, app_commands.CheckFailure):
            await send(
                "You are not allowed to use that command here. Try again in the appropriate channel."
            )
            interaction.extras["error_handled"] = True
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerFinder(bot))
