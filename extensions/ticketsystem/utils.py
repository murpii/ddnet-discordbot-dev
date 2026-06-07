import aiohttp
import contextlib
import logging
import sqlite3
import discord
import re
from datetime import datetime, timezone

from utils.misc import get_filename_from_header, ip_matches

log = logging.getLogger(__name__)

# Synced active-ban list exported from YADDB
BANS_DB_PATH = "data/ticket-system/db.sqlite"


def ban_to_dict(row) -> dict:
    """Turn a raw (ip, name, expires, reason, moderator) row into a ban dict.

    `expires` becomes a timezone-aware datetime (the stored value is naive UTC).
    """
    ip, name, expires, reason, moderator = row
    expires_dt = datetime.fromisoformat(expires) if isinstance(expires, str) else expires
    if expires_dt and expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    return {"ip": ip, "name": name, "expires": expires_dt, "reason": reason, "moderator": moderator}


def find_bans_for_ip(address: str, db_path: str = BANS_DB_PATH) -> list[dict]:
    """Return all ban entries (expired or not) whose ip or range matches address"""
    address = address.strip()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ip, name, expires, reason, moderator FROM bans "  # noqa
            "WHERE ip = ? OR instr(ip, '-') > 0",
            (address,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [ban_to_dict(row) for row in rows if ip_matches(address, row[0])]


def find_active_bans(address: str, db_path: str = BANS_DB_PATH) -> list[dict]:
    """Return matching, non-expired bans for `address`, soonest-expiring first."""
    now = datetime.now(timezone.utc)
    active = [
        ban for ban in find_bans_for_ip(address, db_path)
        if ban["expires"] and ban["expires"] > now
    ]
    active.sort(key=lambda ban: ban["expires"])
    return active


async def find_or_create_category(
        guild: discord.Guild,
        category: discord.CategoryChannel
) -> discord.CategoryChannel | None:
    """
    Finds an available category or creates a new one
    A category is considered available if it has fewer than 50 channels
    """
    if len(category.channels) < 50:
        return category

    try:
        new_category = await guild.create_category(
            name=category.name,
            overwrites=category.overwrites,
            reason="Cloned from existing category",
        )
    except discord.Forbidden:
        log.error(f"Failed to create new ticket category in guild {guild.id}. Bot lacks 'Manage Channels' permission.")
        return None
    except discord.HTTPException as e:
        log.error(f"An HTTP error occurred while creating a category in guild {guild.id}: {e}")
        return None

    # create_category doesn't reliably honour a position arg (the clone sometimes lands
    # above the original because.. only discord knows), so move it right below the original via the reorder endpoint.
    with contextlib.suppress(discord.HTTPException):
        await new_category.move(after=category, reason="Keep the overflow category below the original")

    return new_category


async def fetch_rank_from_demo(bot, message: discord.Message, session: aiohttp.ClientSession):
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
