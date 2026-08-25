import discord
from discord import app_commands
from discord.ext import commands
import ipaddress
import re
from urllib.parse import urlsplit

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


def missing_permissions(channel, *required: str) -> list[str]:
    """Which of the required permissions the bot does not have in a channel.

    Args:
        channel: Any guild channel or thread.
        *required: discord.Permissions attribute names, e.g. "manage_messages".

    Returns:
        The missing names, in the order they were passed.
    """
    permissions = channel.permissions_for(channel.guild.me)
    return [name for name in required if not getattr(permissions, name)]


def permission_report(channel, *required: str) -> str:
    """What the bot is missing in a channel and what it has there.

    Meant to be appended to a Forbidden error message, so whoever sees it can
    fix the channel overwrites without guessing. With no required names it
    only lists what the bot has.
    """
    permissions = channel.permissions_for(channel.guild.me)
    granted = sorted(name for name, allowed in permissions if allowed)

    lines = []
    if required:
        missing = missing_permissions(channel, *required)
        lines.append(
            f"Missing in {channel.mention}: {', '.join(missing)}" if missing else
            f"Has all of {', '.join(required)}, so this is more likely role hierarchy "
            f"or an overwrite on the target than a channel permission."
        )
    lines.append(f"-# {channel.mention} permissions: {', '.join(granted) or 'none'}")
    return "\n".join(lines)


def api_routes() -> list[tuple]:
    return [
        ("POST", r"/channels/\d+/messages/bulk-delete$", ("manage_messages", "read_message_history")),
        ("DELETE", r"/channels/\d+/messages/\d+/reactions", ("manage_messages",)),
        ("PUT", r"/channels/\d+/messages/\d+/reactions/", ("add_reactions", "read_message_history")),
        ("POST", r"/channels/\d+/messages/\d+/threads$", ("create_public_threads",)),
        ("DELETE", r"/channels/\d+/messages/\d+$", ("manage_messages",)),
        ("POST", r"/channels/\d+/messages$", ("view_channel", "send_messages")),
        ("GET", r"/channels/\d+/messages", ("view_channel", "read_message_history")),
        ("PUT|DELETE", r"/channels/\d+/permissions/\d+$", ("manage_roles",)),
        ("PUT|DELETE", r"/channels/\d+/pins/\d+$", ("manage_messages",)),
        ("GET|POST", r"/channels/\d+/webhooks$", ("manage_webhooks",)),
        ("POST", r"/channels/\d+/invites$", ("create_instant_invite",)),
        ("POST", r"/channels/\d+/threads$", ("create_public_threads",)),
        ("POST", r"/channels/\d+/typing$", ("send_messages",)),
        ("PATCH|DELETE", r"/channels/\d+$", ("manage_channels",)),
        ("PUT|DELETE", r"/guilds/\d+/bans/\d+$", ("ban_members",)),
        ("DELETE", r"/guilds/\d+/members/\d+$", ("kick_members",)),
        ("PUT|DELETE", r"/guilds/\d+/members/\d+/roles/\d+$", ("manage_roles",)),
        # one route covers nickname, roles and timeouts, so all three are candidates
        ("PATCH", r"/guilds/\d+/members/\d+$", ("manage_roles", "manage_nicknames", "moderate_members")),
        ("POST", r"/guilds/\d+/channels$", ("manage_channels",)),
        ("GET", r"/guilds/\d+/audit-logs$", ("view_audit_log",)),
        ("PATCH", r"/guilds/\d+$", ("manage_guild",)),
    ]


def route_permissions(method: str, url: str) -> list[str]:
    """Permissions Discord checks for an API route.

    Discord's 403 body never says which permission was missing, but the route
    it blocked does, so map that route back to what it needs.

    Args:
        method: HTTP method of the blocked request.
        url: Its URL or path.

    Returns:
        The permission names, empty if the route is not in api_routes().
    """
    path = urlsplit(str(url)).path
    method = method.upper()
    for methods, pattern, permissions in api_routes():
        if method in methods.split("|") and re.search(pattern, path):
            return list(permissions)
    return []


def forbidden_report(error, channel=None) -> str:
    """Why a 403 probably happened, worked out from the request it blocked.

    Args:
        error: The discord.Forbidden that was raised.
        channel: Where it happened, so the report can list real permissions.

    Returns:
        A short report, empty if the route is unknown and there is no channel.
    """
    response = getattr(error, "response", None)
    method = (getattr(response, "method", "") or "").upper()
    path = urlsplit(str(getattr(response, "url", "") or "")).path
    needed = route_permissions(method, path)

    if channel is None or getattr(channel, "guild", None) is None:
        if not needed:
            return ""
        return f"Blocked request {method} {path} needs: {', '.join(needed)}"

    return permission_report(channel, *needed)


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
