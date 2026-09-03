import asyncio
import contextlib
import functools
import ipaddress
import logging
import os
import urllib.parse
from asyncio.subprocess import PIPE
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Tuple

import discord

from constants import Channels, Emojis, URLs
from utils.countryflags import flag_by_ident
from utils.text import difficulty_stars, slugify2

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)

# Seconds of message history to delete on ban/kick. Used in a lot of modules, don't delete
DELETE_HISTORY_SECONDS = [0, 3600, 21600, 43200, 86400, 259200, 604800]


async def resolve_active_thread(bot: "DDNet", channel_id):
    """Resolve a channel or thread by id, even if it's an archived thread"""
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            log.warning("Could not fetch channel %s: %s", channel_id, e)
            return None

    if isinstance(channel, discord.Thread) and channel.archived:
        with contextlib.suppress(discord.HTTPException):
            # auto_archive_duration is in minutes; 10080 == 7 days (the max).
            await channel.edit(archived=False, auto_archive_duration=10080)

    return channel


async def log_to(bot: "DDNet", thread_id, **send_kwargs):
    """
    Send a staff-log message to one of the LOGS sub-threads
    Falls back to the main LOGS channel when the id is unset (0) or can't be resolved
    """
    target = await resolve_active_thread(bot, thread_id) if thread_id else None
    if target is None:
        target = await resolve_active_thread(bot, Channels.LOGS)
    return None if target is None else await target.send(**send_kwargs)


def get_mapper_urls(maps_data, map_name):
    for info in maps_data:
        if info["Map"] == map_name:
            mappers = info["Mapper"].replace(" & ", ", ").split(", ")
            return [
                f"[{m}](https://ddnet.org/mappers/{slugify2(m)})"
                for m in mappers
            ]
    return []


def resolve_display_name(user: discord.abc.User) -> str:
    """Return the best available visible name for nickname history."""
    if isinstance(user, discord.Member) and user.nick:
        return user.nick
    return user.global_name or user.name


def parse_content_disposition(header_value: str):
    """Parses the Content-Disposition header using basic logic"""
    parts = header_value.split(";")
    params = {}

    for part in parts[1:]:
        if '=' in part:
            key, value = part.strip().split("=", 1)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            params[key.lower()] = value

    return parts[0].strip().lower(), params


async def get_filename_from_header(session, url: str):
    async with session.head(url) as resp:
        if resp.status != 200:
            return None

        cd = resp.headers.get('Content-Disposition', '')
        filename = None

        if cd:
            _, params = parse_content_disposition(cd)

            if 'filename*' in params:
                # RFC 5987 encoding: filename*=utf-8''encoded_filename
                _, _, encoded_filename = params['filename*'].partition("''")
                filename = urllib.parse.unquote(encoded_filename)
            elif 'filename' in params:
                filename = params['filename']

        if not filename:
            parsed_url = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed_url.path)

        return filename


def check_os() -> Tuple[str, str]:
    if os.name == "posix":  # Unix-like system
        shell = "/bin/bash"
        ext = ""
    elif os.name == 'nt':  # Windows
        shell = "powershell.exe"
        ext = ".exe"
    else:
        raise OSError("Unsupported operating system")
    return shell, ext


SHELL, _ = check_os()


async def run_process_shell(cmd: str, timeout: float = 90.0) -> Tuple[str, str]:
    if os.name == 'posix':
        sequence = f"{SHELL} -c '{cmd}'"
        proc = await asyncio.create_subprocess_shell(sequence, stdout=PIPE, stderr=PIPE)
    else:  # Windows
        proc = await asyncio.create_subprocess_exec(SHELL, '-Command', cmd, stdout=PIPE, stderr=PIPE)

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Process timed out") from e
    else:
        return stdout.decode(), stderr.decode()


async def run_process_exec(program: str, *args: str, timeout: float = 90.0) -> Tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(program, *args, stdout=PIPE, stderr=PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Process timed out") from e
    else:
        return stdout.decode(errors="replace"), stderr.decode(errors="replace")


def executor(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        fn = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, fn)

    return wrapper


def rating() -> list:
    return [
        discord.SelectOption(label=f"Rating: {difficulty_stars(value + 1)}", value=str(value))
        for value in range(5)
    ]


def duration() -> list:
    return [
        discord.app_commands.Choice(name="For 30 minutes", value=0),
        discord.app_commands.Choice(name="For 1 hour", value=1),
        discord.app_commands.Choice(name="For 6 Hours", value=2),
        discord.app_commands.Choice(name="For 12 Hours", value=3),
        discord.app_commands.Choice(name="For 24 Hours", value=4),
        discord.app_commands.Choice(name="For 3 Days", value=5),
        discord.app_commands.Choice(name="For 7 Days", value=6),
        discord.app_commands.Choice(name="For 14 Days", value=7),
        discord.app_commands.Choice(name="For 30 Days", value=8)
    ]


def history() -> list:
    return [
        discord.app_commands.Choice(name="Don't Delete Any", value=0),
        discord.app_commands.Choice(name="Previous Hour", value=1),
        discord.app_commands.Choice(name="Previous 6 Hours", value=2),
        discord.app_commands.Choice(name="Previous 12 Hours", value=3),
        discord.app_commands.Choice(name="Previous 24 Hours", value=4),
        discord.app_commands.Choice(name="Previous 3 Days", value=5),
        discord.app_commands.Choice(name="Previous 7 Days", value=6)
    ]


def flag(ident) -> str:
    return flag_by_ident(ident, f"<:flag_unk:{Emojis.FLAG_UNK}>")


def connect_url(addr: str) -> str:
    return f"{URLs.DDNET_CONNECT}?addr={addr}"


def ip_matches(ip: str, target: str) -> bool:
    ip = ip.strip()
    target = target.strip()

    if ip == target:
        return True

    if "-" in target:
        start_ip, end_ip = target.split("-", 1)
        try:
            start = int(ipaddress.IPv4Address(start_ip.strip()))
            end = int(ipaddress.IPv4Address(end_ip.strip()))
            current = int(ipaddress.IPv4Address(ip))
            return start <= current <= end
        except ipaddress.AddressValueError:
            return False

    return False


def to_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def name_filter(player_name: str) -> bool:
    f = {
        "nameless tee", "brainless tee", "nameless", "dummy",
        *{f"({i})nameless tee" for i in range(1, 30)},
        *{f"({i})brainless tee" for i in range(1, 30)},
    }
    return len(player_name) < 4 or player_name.lower() in f
