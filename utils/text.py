import logging
import re
import dateparser
from typing import Optional
from datetime import datetime, timedelta

import discord

import constants

log = logging.getLogger(__name__)


def render_constants(text: str) -> str:
    """
    Replace {Channels.X} / {Roles.X} / {Emojis.X} placeholders with the real
    IDs from constants.py, so e.g. "<#{Channels.WELCOME}>" becomes a working
    channel link.
    """

    def replace(match: re.Match) -> str:
        group = getattr(constants, match[1], None)
        value = getattr(group, match[2], None) if group else None
        if value is None:
            log.warning("render_constants: unknown placeholder %s", match[0])
            return match[0]
        # Emojis/Channels/Roles are IntEnums, format as the plain ID
        return str(int(value)) if isinstance(value, int) else str(value)

    return re.compile(r"\{(Channels|Roles|Emojis)\.([A-Za-z0-9_]+)\}").sub(replace, text)


def humanize_points(points: int) -> str:
    if points < 1000:
        return str(points)
    points = round(points / 1000, 1)
    if points % 1 == 0:
        points = int(points)

    return f"{points}K"


def slugify2(name: str) -> str:
    x = "[\t !\"#$%&'()*-/<=>?@[\\]^_`{|},.:]+"
    return "".join(f"-{ord(c)}-" if c in x or ord(c) >= 128 else c for c in name)


def escape_backticks(text: str) -> str:
    return text.replace("`", "`\u200b")


def inline_code(text: str) -> str:
    if not text:
        return "` `"

    longest_run = 0
    current_run = 0
    for char in text:
        if char == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    fence = "`" * (longest_run + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def escape_custom_emojis(text: str) -> str:
    return re.sub(
        r"<(a)?:([a-zA-Z0-9_]+):([0-9]{17,21})>", r"<%s\1:\2:\3>" % "\u200b", text
    )


def escape(text: str, markdown: bool = True, mentions: bool = True, custom_emojis: bool = True) -> str:
    if markdown:
        text = discord.utils.escape_markdown(text)
    if mentions:
        text = discord.utils.escape_mentions(text)
    if custom_emojis:
        text = escape_custom_emojis(text)

    return text


def escape_link_label(text: str) -> str:
    for char in ("\\", "[", "]", "*", "_", "~", "`", "|"):
        text = text.replace(char, "\\" + char)
    return discord.utils.escape_mentions(text)


def plural(value: int, singular: str) -> str:
    return singular if abs(value) == 1 else f"{singular}s"


def human_timedelta(seconds: float, brief: bool = False) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    units = {
        " day": days,
        " hour": hours,
        " minute": minutes,
        " second": seconds,
    }

    out = " ".join(
        f"{v}{u[1] if brief else plural(v, u)}" for u, v in units.items() if v > 0
    )
    if out:
        return out
    else:
        return "0s" if brief else "0 seconds"


def datetime_to_unix(datetime_str: str) -> int:
    try:
        dt = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
        return int(dt.timestamp())
    except ValueError as e:
        dt = dateparser.parse(datetime_str)
        if not dt:
            now = datetime.now().strftime("%Y/%m/%d %H:%M")
            raise ValueError(
                f"Invalid date/time format. Expected either:\n"
                f"• `YYYY/MM/DD HH:MM` (e.g. `{now}`)\n"
                f"• or natural language like `next week`, `tomorrow 18:00`, etc.\n\n"
                f"Got: `{datetime_str}`"
            ) from e
        return int(dt.timestamp())


def to_discord_timestamp(dt: datetime, style: str = 'f') -> str:
    """
    Convert a datetime object to a Discord-formatted timestamp string.

    Parameters:
        dt : datetime
            The datetime object to convert. Should be timezone-aware or in UTC.
        style : str, optional
            The Discord timestamp style to use (default is 'f'). Options are:
            - 't' : Short time (e.g. 16:20)
            - 'T' : Long time (e.g. 16:20:30)
            - 'd' : Short date (e.g. 20/04/2021)
            - 'D' : Long date (e.g. 20 April 2021)
            - 'f' : Short date/time (e.g. 20 April 2021 16:20)
            - 'F' : Long date/time (e.g. Tuesday, 20 April 2021 16:20)
            - 'R' : Relative time (e.g. 2 months ago, in 10 minutes)

    Returns:
        str: A Discord timestamp string in the format `<t:unix_timestamp:style>`.
    """
    unix_ts = int(dt.timestamp())
    return f"<t:{unix_ts}:{style}>"


def choice_to_datetime(expiry_choice: int) -> datetime:
    now = datetime.now()
    if expiry_choice == 0:
        return now + timedelta(minutes=30)
    elif expiry_choice == 1:
        return now + timedelta(hours=1)
    elif expiry_choice == 2:
        return now + timedelta(hours=6)
    elif expiry_choice == 3:
        return now + timedelta(hours=12)
    elif expiry_choice == 4:
        return now + timedelta(days=1)
    elif expiry_choice == 5:
        return now + timedelta(days=3)
    elif expiry_choice == 6:
        return now + timedelta(days=7)
    elif expiry_choice == 7:
        return now + timedelta(days=14)
    elif expiry_choice == 8:
        return now + timedelta(days=30)
    else:
        raise ValueError("Invalid choice for expiry duration.")


def choice_to_timedelta(duration_choice: int) -> tuple:
    if duration_choice == 0:
        return 60 * 5, "5 minutes"  # 5 minutes
    elif duration_choice == 1:
        return 60 * 10, "10 minutes"  # 10 minutes
    elif duration_choice == 2:
        return 60 * 30, "30 minutes"  # 30 minutes
    elif duration_choice == 3:
        return 60 * 60, "1 hour"  # 1 hour
    elif duration_choice == 4:
        return 60 * 60 * 2, "2 hours"  # 2 hours
    else:
        raise ValueError("Invalid choice for auto-disable duration.")


def strip_surrounding_quotes(s):
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s


def extract_address(string: str) -> Optional[str]:
    pattern = r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5})"
    return match.group(1) if (match := re.search(pattern, string)) else None


def clip(text: str, limit: int = 150) -> str:
    """
    Collapse text onto one line and cap its length. Used by the container
    views, where all text shares one 4000 character budget per message
    """
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


def resolve_role_mentions(content: str, guild: Optional[discord.Guild]) -> str:
    """Replace plain text @RoleName strings with real role mentions"""
    if guild is None or "@" not in content:
        return content
    for role in guild.roles:
        content = content.replace(f"@{role.name}", f"<@&{role.id}>")
    return content


def resolve_user_mentions(content: str, guild: Optional[discord.Guild]) -> tuple:
    """Replace plain-text @username tokens with real user mentions"""
    if guild is None or "@" not in content:
        return content, []

    lookup = {}
    for member in guild.members:
        for name in (member.name, member.nick, member.global_name):
            if name:
                lookup.setdefault(name.lower(), member)
    mentioned = []

    def substitute(match: re.Match) -> str:
        member = lookup.get(match[1].lower())
        if member is None:
            return match[0]
        if member not in mentioned:
            mentioned.append(member)
        return member.mention

    return re.compile(r"@([\w.]{2,32})").sub(substitute, content), mentioned


def parse_message_url(url: str) -> Optional[tuple]:
    url_re = re.compile(r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
    match = url_re.search(url.strip())
    return tuple(int(group) for group in match.groups()) if match else None
