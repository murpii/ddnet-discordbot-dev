import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)

BANS_URL = "https://ddnet.org/bep/mod/bans?format=json"
MOD_PAGE_URL = "https://ddnet.org/bep/mod/"


def ban_to_dict(entry: dict) -> dict:
    """Turn one entry of the website's ban list into a plain ban dict.

    `expires` becomes a timezone-aware datetime, or None for a ban without an end date.
    The "Until <date> UTC" the game server appends to the reason is dropped, since
    `expires` already holds it.
    """
    expires = entry.get("expires_at")
    return {
        "ip": entry["target"],
        "name": entry.get("name"),
        "expires": datetime.fromisoformat(expires) if expires else None,
        "reason": re.sub(r"\. Until .+ UTC$", "", entry.get("reason") or ""),
        "moderator": entry.get("issuer"),
    }


async def fetch_bans(bot: "DDNet") -> list[dict] | None:
    session = await bot.session_manager.get_session("BanList")
    auth = aiohttp.BasicAuth(
        bot.config.get("TICKETS", "USER", fallback=""),
        bot.config.get("TICKETS", "PASSWORD", fallback=""),
    )
    try:
        async with session.get(BANS_URL, auth=auth, timeout=aiohttp.ClientTimeout(total=15)) as response:
            response.raise_for_status()
            entries = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        log.warning("Could not fetch the ban list from %s: %s", BANS_URL, error)
        return None

    return [ban_to_dict(entry) for entry in entries]
