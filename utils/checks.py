import time
import discord
import logging
import functools
import ipaddress
import aiohttp
from typing import Iterable
from constants import Roles


def has_map(message: discord.Message) -> bool:
    return any(
        attachment.filename.endswith(".map")
        for attachment in message.attachments
    )


async def check_dm_channel(user: discord.Member) -> bool:
    try:
        await user.send()
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return True


def measure(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        logging.info(f"{func.__name__} finished in {duration:.2f} seconds")
        return result

    return wrapper


def is_staff(member: discord.abc.User, *, roles: Iterable[int] = None) -> bool:
    """Check if a member has staff roles.

    Args:
        member (discord.Member): The Discord member to check.
        roles (Iterable[int], optional): A collection of role IDs to check against. Defaults to all Staff IDs from DDNet.

    Returns:
        bool: True if the member has at least one of the specified roles, False otherwise.
    """

    staff = [
        Roles.ADMIN,
        Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
        Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
        Roles.MODERATOR, Roles.DISCORD_MODERATOR
    ]

    # Users don’t have roles, so immediately return False
    if not isinstance(member, discord.Member):
        return False

    if roles is None:
        roles = staff

    return any(r.id in roles for r in member.roles)


def check_public_ip(ip: str) -> (bool, str | None):
    """
    Checks if the provided IP address is a public IP.

    Args:
        ip (str): The IP address to check.

    Returns:
        tuple: A tuple containing a boolean indicating if the IP is public and an optional message.
            - bool: True if the IP is public, False otherwise.
            - str | None: A message explaining the result or None if no message is needed.
    """

    if ip == "DEBUG":
        return True, None

    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private:
            return False, (
                f"The IP address {ip} is within a private network range. "
                f"Use https://ipinfo.io/ip to figure out your public IP address."
            )
        return True, None
    except ValueError:
        return False, "Invalid IP address format."


async def check_ip(ip_address, session: aiohttp.ClientSession, api_key: str) -> tuple[str, bool]:
    """|coro|
    Checks if the provided IP address is associated with a Tor network, VPN, or data center.
    Sets self.is_blocked to a status message and returns (status message, is_cloudflare).

    Args:
        ip_address: The IP address to check.
        session: The aiohttp session to use.
        api_key: The API key to use.

    Returns:
        tuple[str, bool]:
            - str: DNSBL status ("DNSBL=black", "DNSBL=white", or "DNSBL=error").
            - bool: True if the IP belongs to Cloudflare, False otherwise.
    """
    url = f'https://api.ipapi.is/?q={ip_address}&key={api_key}'
    resp = await session.get(url)
    js = await resp.json()

    if resp.status == 200:
        if js.get('is_tor') or js.get('is_vpn') or js.get('is_datacenter'):
            datacenter_info = js.get('datacenter')
            is_cloudflare = bool(datacenter_info and 'cloudflare' in datacenter_info.get('datacenter', '').lower())
            dnsbl = "DNSBL=black"
            return dnsbl, is_cloudflare
        else:
            dnsbl = "DNSBL=white"
            return dnsbl, False
    else:
        dnsbl = "DNSBL=error"
        return dnsbl, False
