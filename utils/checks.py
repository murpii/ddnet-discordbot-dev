import discord
from discord import app_commands
from discord.ext import commands
import ipaddress
import aiohttp
from typing import Iterable
from constants import Roles, Guilds, WIKI_CURATOR_ROLES


def ddnet_only(ctx: commands.Context) -> bool:
    return ctx.guild.id == Guilds.DDNET


async def check_dm_channel(user: discord.Member) -> bool | None:
    try:
        await user.send()
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return True


def staff_roles(group: str = "staff") -> list[int]:
    """Role IDs of a named staff group. is_staff() takes these names directly.

    Args:
        group (str): Which group to return.
            "staff"        == every staff role, testers included.
            "admins"       == admins only.
            "mods"         == admins and both kinds of moderator.
            "discord_mods" == runs the Discord server itself, so bans, unbans, kicks,
                              channel tools and the blacklist. Roles.MODERATOR is a
                              game-server moderator and stays out of this group.
            "game_mods"    == admins and game-server moderators, for the player finder
                              and the game-server logs.
            "testers"      == admins and full testers.
            "wiki_curators" == admins and the wiki curators, who hand out the
                              Wiki Contributor role.

    Returns:
        list[int]: The role IDs in that group.
    """

    groups = {
        "staff": [
            Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR,
            Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
            Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
        ],
        "mods": [Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR],
        "discord_mods": [Roles.ADMIN, Roles.DISCORD_MODERATOR],
        "game_mods": [Roles.ADMIN, Roles.MODERATOR],
        "testers": [Roles.ADMIN, Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS],
        "admins": [Roles.ADMIN],
        "wiki_curators": [Roles.ADMIN, *WIKI_CURATOR_ROLES],
    }
    return groups[group]


def is_staff(member: discord.abc.User, *, roles: Iterable[int] | str = None) -> bool:
    """Check if a member has staff roles.

    Args:
        member (discord.Member): The Discord member to check.
        roles (optional): A collection of role IDs to check against, or the name of a
            staff_roles() group. Defaults to all Staff IDs from DDNet.

    Returns:
        bool: True if the member has at least one of the specified roles, False otherwise.
    """

    # Users don’t have roles, so immediately return False
    if not isinstance(member, discord.Member):
        return False

    if roles is None:
        wanted = staff_roles()
    elif isinstance(roles, str):
        wanted = staff_roles(roles)
    else:
        wanted = list(roles)

    return any(r.id in wanted for r in member.roles)


def staff_only(group: str = "staff"):
    """App command decorator gating on a staff_roles() group.

    It also records the group name on the callback, so /help can hide the command
    from members who could not run it anyway. Use this instead of applying
    app_commands.checks.has_any_role directly, otherwise /help has no way to tell
    the command is staff only.
    """

    def decorator(func):
        # applied above @app_commands.command it gets a Command, below it a function
        target = getattr(func, "callback", func)
        target.__staff_group__ = group
        return app_commands.checks.has_any_role(*staff_roles(group))(func)

    return decorator


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

    if resp.status != 200:
        return "DNSBL=error", False
    if (
            not js.get('is_tor')
            and not js.get('is_vpn')
            and not js.get('is_datacenter')
    ):
        return "DNSBL=white", False
    datacenter_info = js.get('datacenter')
    is_cloudflare = bool(datacenter_info and 'cloudflare' in datacenter_info.get('datacenter', '').lower())
    dnsbl = "DNSBL=black"
    return dnsbl, is_cloudflare
