import asyncio
import io
import ipaddress
import logging
import re
import socket

import discord

from constants import Channels
from extensions.management.hub import HubButton
from utils.containers import INFO_ACCENT, NoticeView, separator
from utils.gamelog import build_log, filter_log
from utils.master_parser import (
    AddressParseError,
    community_ips,
    fetch_master_list_safe,
    find_servers_by_community,
    parse_address,
)
from utils.misc import log_to

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()

LOG_DIR = "servers/servers"
FETCH_BYTE_CAP = 8 * 1024 * 1024
SSH_TIMEOUT = 25
SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=5",
    "-o", "StrictHostKeyChecking=accept-new",
]

FILTER_TIMEOUT = 900
MAX_CONTEXT = 30

SHOW_ALL = "all"
KIND_LABELS = {
    "chat": "chat only",
    "connections": "joins and leaves only",
    "system": "votes and kicks only",
}


def location_hosts(bot: "DDNet") -> list[str]:
    path = bot.config.get("GAMESERVERS", "ALL_LOCATIONS_FILE", fallback="")
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as file:
            return file.readline().split()
    except OSError:
        log.warning("ServerLogs: could not read the all-locations file at %s", path)
        return []


async def resolve_ips(domain: str) -> list[str]:
    loop = asyncio.get_running_loop()
    ips = []
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = await loop.getaddrinfo(domain, None, family=family)
        except OSError:
            continue
        ips += [info[4][0] for info in infos]
    return ips


def ssh_command(bot: "DDNet", ssh_host: str, remote_command: str) -> list[str]:
    command = ["ssh", *SSH_OPTIONS]
    ssh_port = bot.config.get("GAMESERVERS", "SSH_PORT", fallback="")
    if ssh_port:
        command += ["-p", ssh_port]
    key_file = bot.config.get("GAMESERVERS", "SSH_KEY_FILE", fallback="").strip('"')
    if key_file:
        command += ["-i", key_file]
    user = bot.config.get("GAMESERVERS", "SSH_USER", fallback="")
    command.append(f"{user}@{ssh_host}" if user else ssh_host)
    command.append(remote_command)
    return command


async def fetch_log(bot: "DDNet", ssh_host: str, port: int) -> tuple[str, str]:
    remote_command = f"cat {LOG_DIR}/{port}.log 2>/dev/null | tail -c {FETCH_BYTE_CAP}"
    process = await asyncio.create_subprocess_exec(
        *ssh_command(bot, ssh_host, remote_command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), SSH_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        return "", f"Timed out fetching the log from {ssh_host}."

    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip().splitlines()
        reason = detail[-1] if detail else "unknown error"
        return "", f"Could not reach {ssh_host}: {reason}"

    text = stdout.decode("utf-8", "replace")
    if not text.strip():
        return "", f"No log found for port {port} on {ssh_host}. Wrong address?"
    return text, ""


def parse_target(raw: str) -> tuple[str, int] | None:
    host, _, port_part = raw.rpartition(":")
    host = host.strip("[]")
    if not host or not port_part.isdigit():
        return None
    port = int(port_part)
    if not 1 <= port <= 65535:
        return None
    return host, port


def find_label_ip(master, label: str, port: int) -> str | None:
    word = re.compile(rf"\b{re.escape(label)}\b", re.IGNORECASE)
    matched_ips = set()
    for server in find_servers_by_community(master, "ddnet"):
        if not word.search(server.info.name):
            continue
        for address in server.addresses:
            try:
                host, server_port = parse_address(address)[3:5]
            except AddressParseError:
                continue
            if server_port == port:
                matched_ips.add(host)
    ipv4 = [ip for ip in matched_ips if ":" not in ip]
    if len(ipv4) == 1:
        return ipv4[0]
    if not ipv4 and len(matched_ips) == 1:
        return matched_ips.pop()
    return None


def server_display_name(master, addresses: list[str]) -> str:
    if master is None or not addresses:
        return ""
    wanted = set(addresses)
    for server in master.servers:
        if server.normalized_address in wanted:
            return server.info.name
    return ""


def context_count(raw: str) -> int:
    raw = raw.strip()
    return min(int(raw), MAX_CONTEXT) if raw.isdigit() else 0


def describe_filter(query: str, names: list[str], kind: str, before: int, after: int) -> str:
    def quoted(text: str) -> str:
        return "`" + text.replace("`", "") + "`"  # a backtick would break the code span

    parts = []
    if query:
        parts.append(quoted(query))
    if names:
        parts.append("from " + ", ".join(quoted(name) for name in names))
    if kind != SHOW_ALL:
        parts.append(KIND_LABELS[kind])
    text = " ".join(parts) if parts else "everything"
    if before or after:
        text += f" (-B{before} -A{after})"
    return text


class LogFilterModal(discord.ui.Modal, title="Filter the log"):
    def __init__(self, source: "ServerLogView"):
        super().__init__(timeout=300)
        self.source = source

        self.search = discord.ui.Label(
            text="Search",
            description="Case insensitive. Wrap in slashes for a regex, e.g. /bot|cheat/",
            component=discord.ui.TextInput(required=False, max_length=200),
        )
        self.players = discord.ui.Label(
            text="Only these players",
            description="Comma separated, partial names are fine",
            component=discord.ui.TextInput(required=False, max_length=200),
        )
        self.before = discord.ui.Label(
            text="Lines before each hit",
            component=discord.ui.TextInput(required=False, max_length=2, placeholder="0"),
        )
        self.after = discord.ui.Label(
            text="Lines after each hit",
            component=discord.ui.TextInput(required=False, max_length=2, placeholder="0"),
        )
        self.kind = discord.ui.Label(
            text="Limit to",
            component=discord.ui.Select(
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label="Everything", value=SHOW_ALL, default=True),
                    discord.SelectOption(label="Chat only", value="chat"),
                    discord.SelectOption(label="Joins and leaves only", value="connections"),
                    discord.SelectOption(label="Votes and kicks only", value="system"),
                ],
            ),
        )
        for item in (self.search, self.players, self.before, self.after, self.kind):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = self.search.component.value.strip()
        names = [name.strip() for name in self.players.component.value.split(",") if name.strip()]
        kind = self.kind.component.values[0]
        before = context_count(self.before.component.value)
        after = context_count(self.after.component.value)

        if not query and not names and kind == SHOW_ALL:
            await interaction.response.send_message(
                view=NoticeView("Give me something to filter on: a search text, a player, or a category."),
                ephemeral=True,
            )
            return

        try:
            lines, hits = filter_log(
                self.source.keys, self.source.lines,
                query=query, names=names, kind=kind, before=before, after=after,
            )
        except re.error as exc:
            await interaction.response.send_message(
                view=NoticeView(f"That regex is not valid: `{exc}`"), ephemeral=True,
            )
            return

        if not hits:
            criteria = describe_filter(query, names, kind, before, after)
            await interaction.response.send_message(
                view=NoticeView(f"Nothing in this log matches {criteria}."), ephemeral=True,
            )
            return

        body = "\n".join(lines).encode("utf-8")
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(body), filename=self.source.filtered_name),
            ephemeral=True,
        )


class FilterButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Filter", style=discord.ButtonStyle.primary, emoji="\U0001f50d")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(LogFilterModal(self.view))


class ServerLogView(discord.ui.LayoutView):
    def __init__(self, summary: str, keys: list, lines: list[str], filename: str):
        super().__init__(timeout=FILTER_TIMEOUT)
        self.keys = keys
        self.lines = lines
        self.filtered_name = filename.replace(".diff", "_filtered.diff")
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(summary),
            separator(),
            discord.ui.ActionRow(FilterButton()),
            accent_colour=INFO_ACCENT,
        ))


class ServerLogsModal(discord.ui.Modal, title="Fetch a server log"):
    def __init__(self, bot: "DDNet"):
        super().__init__(timeout=300)
        self.bot = bot

        names = location_hosts(bot)
        if len(names) > 25:
            log.warning("ServerLogs: %d locations, a select holds 25, use the address box for the rest", len(names))
            names = names[:25]
        self.location = discord.ui.Label(
            text="Location",
            component=discord.ui.Select(
                required=False,
                placeholder="Pick the server's location",
                options=[discord.SelectOption(label=name.upper(), value=name) for name in names],
            ),
        )
        self.port = discord.ui.Label(
            text="Port",
            description="The server's port, e.g. 8303",
            component=discord.ui.TextInput(required=False, max_length=5),
        )
        self.address = discord.ui.Label(
            text="Or type the server instead",
            description="ip:port, or the name label and port, e.g. GER:8303 for DDNet GER - Brutal",
            component=discord.ui.TextInput(required=False, max_length=60),
        )
        for item in (self.location, self.port, self.address):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        picked = self.location.component.values
        port_text = self.port.component.value.strip()
        pasted = self.address.component.value.strip()

        if picked and port_text:
            if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
                await interaction.response.send_message(
                    view=NoticeView(f'"{port_text}" is not a valid port.'), ephemeral=True,
                )
                return
            host_part, port = picked[0], int(port_text)
            raw = f"{picked[0]}:{port}"
        elif pasted:
            target = parse_target(pasted)
            if target is None:
                await interaction.response.send_message(
                    view=NoticeView(f'"{pasted}" is not a valid address. Use ip:port, e.g. `45.141.57.22:8303`.'),
                    ephemeral=True,
                )
                return
            host_part, port = target
            raw = pasted
        else:
            await interaction.response.send_message(
                view=NoticeView("Pick a location and type the port, or paste a full ip:port address."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.deliver_log(interaction, raw, host_part, port)
        except Exception:
            log.exception("ServerLogs: fetching %s failed", raw)
            await interaction.edit_original_response(
                view=NoticeView("Something went wrong fetching that log, check the bot log.")
            )

    async def deliver_log(self, interaction, raw, host_part, port):
        try:
            ipaddress.ip_address(host_part)
            is_ip = True
        except ValueError:
            is_ip = False

        session = await self.bot.session_manager.get_session("ServerLogs")
        master = await fetch_master_list_safe(session)

        if is_ip:
            if master is None:
                await interaction.edit_original_response(
                    view=NoticeView("Could not verify the address against the master server list, try again later.")
                )
                return
            if host_part not in community_ips(master, "ddnet"):
                await interaction.edit_original_response(
                    view=NoticeView(f"`{host_part}` is not an official DDNet server address.")
                )
                return
            ssh_host = host_part
        else:
            name = host_part.removesuffix(".ddnet.org").lower()
            if name in location_hosts(self.bot):
                ssh_host = f"{name}.ddnet.org"
            else:
                if master is None:
                    await interaction.edit_original_response(
                        view=NoticeView("Could not check the master server list, try again later.")
                    )
                    return
                label_ip = find_label_ip(master, name, port)
                if label_ip is None:
                    await interaction.edit_original_response(
                        view=NoticeView(
                            f'Could not find an official "{host_part}" server on port {port}. '
                            "Paste the exact ip:port instead."
                        )
                    )
                    return
                ssh_host = label_ip

        raw_log, error = await fetch_log(self.bot, ssh_host, port)
        if error:
            await interaction.edit_original_response(view=NoticeView(error))
            return

        keys, lines = build_log(raw_log)
        if not lines:
            await interaction.edit_original_response(
                view=NoticeView(f"The current log of {raw} contains no chat, joins or votes.")
            )
            return

        if ssh_host.endswith(".ddnet.org"):
            candidate_ips = await resolve_ips(ssh_host)
        else:
            candidate_ips = [ssh_host]
        addresses = [f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}" for ip in candidate_ips]
        server_name = server_display_name(master, addresses)

        summary = [f"## Server log: `{raw}`"]
        if server_name:
            summary.append(f"**Server:** {server_name}")
        summary.append(f"**Fetched from:** {ssh_host}, current session")
        summary.append(f"**Lines:** {len(lines)}")
        summary.append("-# Cleaned to player chat, joins (+) and leaves (-) with address, votes and kicks.")
        summary.append(
            f"-# Filter searches this log without re-fetching it. "
            f"Expires after {FILTER_TIMEOUT // 60} minutes without a press."
        )

        safe_host = ssh_host.removesuffix(".ddnet.org").replace(":", "-")
        filename = f"{safe_host}_{port}.diff"
        logfile = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=filename)
        await interaction.edit_original_response(
            view=ServerLogView("\n".join(summary), keys, lines, filename)
        )
        await interaction.followup.send(file=logfile, ephemeral=True)

        log.info("ServerLogs: %s fetched %s (%s)", interaction.user, raw, ssh_host)
        await log_to(
            self.bot, Channels.LOG_MOD_ACTIONS,
            view=NoticeView(
                f"{interaction.user.mention} fetched the server log of `{raw}` ({ssh_host})."),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class ServerLogsButton(HubButton):
    def __init__(self, bot: "DDNet"):
        super().__init__(
            bot, label="Fetch logs", custom_id="ModHub:server-logs",
            style=discord.ButtonStyle.primary, roles="game_mods",  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        if not location_hosts(self.bot):
            await interaction.response.send_message(
                view=NoticeView("Log fetching is not configured (GAMESERVERS in config.ini)."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ServerLogsModal(self.bot))
