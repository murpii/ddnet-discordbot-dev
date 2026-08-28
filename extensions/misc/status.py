import discord
from discord.ext import commands
from discord import app_commands
import logging
from collections import namedtuple
from datetime import datetime, timezone
from typing import Dict, List, Optional, TYPE_CHECKING

from constants import Emojis
from utils.countryflags import flag_by_code
from utils.containers import NoticeView
from utils.text import to_discord_timestamp

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)

BASE_URL = "https://ddnet.org"


class ServerInfo:
    __slots__ = ("host", "online", "packets")

    Packets = namedtuple("Packets", "rx tx")

    PPS_THRESHOLD = 10000  # china got alot players
    PPS_RATIO_MIN = 1000  # ratio is not reliable for low traffic
    PPS_RATIO_THRESHOLD = (
        2.5  # responding to less than half the traffic indicates junk traffic
    )

    def __init__(self, **kwargs):
        self.host = kwargs.pop("type")
        self.online = kwargs.pop("online4")

        self.packets = self.Packets(
            kwargs.pop("packets_rx", -1), kwargs.pop("packets_tx", -1)
        )

    def __str__(self) -> str:
        return "MAIN" if self.host == "ddnet.org" else self.host.split(".")[0].upper()

    def is_under_attack(self) -> bool:
        return (
                self.packets.rx > self.PPS_THRESHOLD
                or self.packets.rx > self.PPS_RATIO_MIN
                and self.packets.rx / self.packets.tx > self.PPS_RATIO_THRESHOLD
        )

    @property
    def status(self) -> str:
        if not self.online:
            return "down"
        elif self.is_under_attack():
            return "ddos"  # not necessarily correct but easy to understand
        else:
            return "up"

    @property
    def flag(self) -> str:
        if str(self) in {"MAIN", "MASTER", "DB"}:
            return flag_by_code("EU")
        else:
            return flag_by_code(str(self)[:3], f"<:flag_unk:{Emojis.FLAG_UNK}>")


class ServerStatus:
    __slots__ = ("servers", "timestamp")

    URL = f"{BASE_URL}/status/"

    def __init__(self, servers: List[Dict], updated: str):
        self.servers = [ServerInfo(**s) for s in servers]
        self.timestamp = datetime.fromtimestamp(float(updated), timezone.utc)

    def build_view(self) -> NoticeView:
        def humanize_pps(pps: int) -> str:
            if pps < 0:
                return ""

            for unit in ("", "k", "m", "g"):
                if pps < 1000:
                    return str(pps) + unit

                pps = round(pps / 1000, 2)

        rows = [
            f"## [Server Status]({self.URL})",
            f"<:flag_unk:{Emojis.FLAG_UNK}> `server| +- | ▲ pps | ▼ pps `",
        ]
        for server in self.servers:
            if server.host:
                rows.append(
                    f"{server.flag} `{str(server):<6}|{server.status:^4}|"
                    f"{humanize_pps(server.packets.rx):>7}|{humanize_pps(server.packets.tx):>7}`"
                )
        rows.append(f"-# Updated {to_discord_timestamp(self.timestamp, 'R')}")

        return NoticeView("\n".join(rows))


class Status(commands.Cog, name="DDNet Status"):
    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = await self.bot.session_manager.get_session(self.__class__.__name__)

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def fetch_status(self) -> Optional[ServerStatus]:
        url = f"{BASE_URL}/status/json/stats.json"
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error(
                    "Failed to fetch DDNet status data (status code: %d %s)",
                    resp.status,
                    resp.reason,
                )
                raise RuntimeError("Could not fetch DDNet status")

            js = await resp.json()

            return ServerStatus(**js)

    @app_commands.command(name="ddos", description="Display DDNet server status")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def ddos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            status = await self.fetch_status()
        except RuntimeError as exc:
            await interaction.followup.send(exc)
        else:
            await interaction.followup.send(view=status.build_view())

        if interaction.response.is_done():  # noqa
            return


async def setup(bot: "DDNet"):
    await bot.add_cog(Status(bot))
