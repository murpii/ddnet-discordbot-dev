import asyncio
import contextlib
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord

from utils.bans import fetch_bans
from utils.misc import ip_matches, run_process_exec

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


FINISH_LINE = re.compile(
    r"^\[[\d:]+\] chat: \*\*\* (?:\[D\] )?(?P<name>.+) finished in: "
    r"(?P<minutes>\d+) minute\(s\)\s+(?P<seconds>\d+(?:\.\d+)?) second\(s\)$"
)


async def fetch_rank_from_demo(
        bot: "DDNet",
        message: discord.Message,
        session: aiohttp.ClientSession,
        names: tuple[str, ...],
):
    """Return (demo name, player name, time in seconds, timestamp or None) for finishes of `names`."""
    data_folder = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    tool = shutil.which("demo_extract_chat", path=data_folder)
    if not tool:
        log.warning(
            f"demo_extract_chat was not found or is not executable in {os.path.abspath(data_folder)}, "
            "can't read demo finishes"
        )
        return []

    finishes = []
    for attachment in message.attachments:
        if not attachment.filename.endswith(".demo"):
            continue

        with tempfile.TemporaryDirectory() as folder:
            demo_path = os.path.join(folder, "demo.demo")
            async with session.get(attachment.url) as response:
                with open(demo_path, "wb") as demo_file:
                    demo_file.write(await response.read())
            output, error = await run_process_exec(tool, demo_path)

        if not output.strip():
            log.warning(f"demo_extract_chat gave no output for {attachment.filename}: {error.strip()}")

        for line in output.splitlines():
            match = FINISH_LINE.match(line)
            if match and match["name"] in names:
                seconds = int(match["minutes"]) * 60 + float(match["seconds"])
                finishes.append((attachment.filename, match["name"], seconds))

    results = []
    for demo, name, seconds in finishes:
        query = """
                SELECT Timestamp
                FROM record_race
                WHERE Name = %s
                  AND ABS(Time - %s) < 0.01
                LIMIT 1 \
                """
        row = await bot.fetch(query, name, seconds, fetchall=False)
        results.append((demo, name, seconds, row[0] if row else None))

    return results


def format_finishes(finishes) -> list[str]:
    """Return the finish lines split into messages that fit Discord's 2000 character limit."""
    lines = ["✅ Finishes found in demos:"] + [
        f"- `{demo}` `{name}` {seconds:.2f}s (Timestamp: `{timestamp or 'not in database'}`)"
        for demo, name, seconds, timestamp in finishes
    ]

    messages = []
    current = ""
    for line in lines:
        line = line[:1900]
        if current and len(current) + len(line) + 1 > 1900:
            messages.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    messages.append(current)
    return messages
