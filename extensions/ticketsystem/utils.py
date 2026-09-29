import asyncio
import contextlib
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord

from utils.bans import fetch_bans
from utils.misc import get_filename_from_header, ip_matches

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)

category_lock = asyncio.Lock()


async def find_bans_for_ip(bot: "DDNet", address: str) -> list[dict] | None:
    """Return all bans (expired or not) whose ip or range matches `address`.

    Returns None when the website's ban list could not be fetched, so callers can
    tell an outage apart from "not banned".
    """
    bans = await fetch_bans(bot)
    if bans is None:
        return None

    address = address.strip()
    return [ban for ban in bans if ip_matches(address, ban["ip"])]


async def find_active_bans(bot: "DDNet", address: str) -> list[dict] | None:
    """Return matching, non-expired bans for `address`, soonest-expiring first.

    A ban without an expiry date is permanent, so it counts as active and sorts last.
    Returns None when the ban list could not be fetched.
    """
    bans = await find_bans_for_ip(bot, address)
    if bans is None:
        return None

    now = datetime.now(timezone.utc)
    active = [ban for ban in bans if ban["expires"] is None or ban["expires"] > now]
    active.sort(key=lambda ban: ban["expires"] or datetime.max.replace(tzinfo=timezone.utc))
    return active


async def find_or_create_category(
        guild: discord.Guild,
        category: discord.CategoryChannel
) -> discord.CategoryChannel | None:
    """
    Finds an available category or creates a new one
    A category is considered available if it has fewer than 50 channels
    """
    async with category_lock:
        candidates = sorted(
            (cat for cat in guild.categories if cat.name == category.name),
            key=lambda cat: cat.position,
        )
        if category not in candidates:
            candidates.insert(0, category)

        for candidate in candidates:
            if len(candidate.channels) < 50:
                return candidate

        last_category = candidates[-1]
        try:
            new_category = await guild.create_category(
                name=category.name,
                overwrites=category.overwrites,
                reason="Cloned from existing category",
            )
        except discord.Forbidden:
            log.error(
                f"Failed to create new ticket category in guild {guild.id}. Bot lacks 'Manage Channels' permission."
            )
            return None
        except discord.HTTPException as e:
            log.error(f"An HTTP error occurred while creating a category in guild {guild.id}: {e}")
            return None

        with contextlib.suppress(discord.HTTPException):
            await new_category.move(after=last_category, reason="Keep the overflow category below the original")

        log.info(f"Created overflow ticket category '{new_category.name}' ({new_category.id})")
        return new_category


async def fetch_rank_from_demo(bot: "DDNet", message: discord.Message, session: aiohttp.ClientSession):
    demo_names = []
    for attachment in message.attachments:
        if attachment.filename.endswith(".demo"):
            filename = await get_filename_from_header(session, url=attachment.url)
            demo_names.append(filename)

    ranks = []

    for demo in demo_names:
        match = re.match(r"(.+?)_(\d+\.\d+)_([^.]+(?:\.+)*)\.demo", demo)
        if not match:
            continue

        map_name, time_str, player_name = match.groups()

        if '.' in time_str:
            time_str = time_str.rstrip('0').rstrip('.')

        map_name = f"%{map_name}%"
        query = """
                SELECT Timestamp
                FROM record_race
                WHERE Map LIKE %s
                  AND Time LIKE %s
                  AND Name = %s \
                """
        result = await bot.fetch(query, map_name, time_str, player_name, fetchall=False)

        if result:
            timestamp = result[0]
            ranks.append((demo, timestamp))

    return ranks
