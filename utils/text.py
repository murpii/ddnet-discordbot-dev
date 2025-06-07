import re
import dateparser
from typing import List, Optional, Union, Iterable
from datetime import datetime, timedelta

import discord
from discord.ext import commands


class CleanContent(commands.clean_content):
    def __init__(self):
        super().__init__(fix_channel_mentions=True)

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        if argument[0] == '"' and argument[-1] == '"':
            argument = argument[1:-1]  # strip quotes

        argument = argument.replace("\ufe0f", "")  # remove VS16
        argument = re.sub(r"<a?(:[a-zA-Z0-9_]+:)[0-9]{17,21}>", r"\1", argument)
        return await super().convert(ctx, argument)


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


def escape_custom_emojis(text: str) -> str:
    return re.sub(
        r"<(a)?:([a-zA-Z0-9_]+):([0-9]{17,21})>", r"<%s\1:\2:\3>" % "\u200b", text
    )


def escape(
    text: str, markdown: bool = True, mentions: bool = True, custom_emojis: bool = True
) -> str:
    if markdown:
        text = discord.utils.escape_markdown(text)
    if mentions:
        text = discord.utils.escape_mentions(text)
    if custom_emojis:
        text = escape_custom_emojis(text)

    return text


def truncate(text: str, *, length: int) -> str:
    return f"{text[:length - 3]}..." if len(text) > length else text


def human_join(seq: List[str], delim: str = ", ", final: str = " & ") -> str:
    size = len(seq)
    if size == 0:
        return ""
    elif size == 1:
        return seq[0]
    elif size == 2:
        return seq[0] + final + seq[1]
    else:
        return delim.join(seq[:-1]) + final + seq[-1]


def sanitize(text: str) -> str:
    return re.sub(r'[\^<>{}"/|;:,.~!?@#$%=&*\]\\()\[+]', "", text.replace(" ", "_"))


def normalize(text: str) -> str:
    return re.sub(rb"[^a-zA-Z0-9]", rb"_", text.encode()).decode()


def plural(value: int, singular: str) -> str:
    return singular if abs(value) == 1 else f"{singular}s"


def render_table(header: List[str], rows: List[List[str]]) -> str:
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(len(header))]

    out = [
        " | ".join(c.center(w) for c, w in zip(header, widths)),
        "-+-".join("-" * w for w in widths),
    ]

    for row in rows:
        columns = []
        for column, width in zip(row, widths):
            try:
                float(column)
            except ValueError:
                columns.append(column.ljust(width))
            else:
                columns.append(column.rjust(width))

        out.append(" | ".join(columns))

    return "\n".join(out)


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


def str_to_timedelta(expiry_date: str) -> timedelta:
    pattern = r'^(\d+)(mo|[mhdw])?$'
    match = re.match(pattern, expiry_date.lower())
    if not match:
        raise ValueError("Invalid expiry date format")

    amount = int(match[1])
    unit = match[2]

    try:
        if unit == "m":
            return timedelta(minutes=amount)
        elif unit == "h":
            return timedelta(hours=amount)
        elif unit == "d":
            return timedelta(days=amount)
        elif unit == "w":
            return timedelta(weeks=amount)
        elif unit == "mo":
            return timedelta(days=amount * 30)
        else:
            # If unit is None or not specified, assume days? Or raise error?
            # Let's assume days if missing:
            return timedelta(days=amount)
    except Exception as e:
        raise ValueError("Invalid expiry date format") from e


def str_to_datetime(expiry_date: str) -> datetime:
    pattern = r'^(\d+)(mo|[mhdw])?$'
    match = re.match(pattern, expiry_date.lower())
    if not match:
        raise ValueError("Invalid expiry date format")

    amount = int(match[1])
    unit = match[2]
    now = datetime.now()

    try:
        if unit == "m":
            return now + timedelta(minutes=amount)
        elif unit == "h":
            return now + timedelta(hours=amount)
        elif unit == "d":
            return now + timedelta(days=amount)
        elif unit == "w":
            return now + timedelta(weeks=amount)
        elif unit == "mo":
            return now + timedelta(days=amount * 30)
        return None
    except ValueError as e:
        raise ValueError("Invalid expiry date format") from e


def datetime_to_unix(datetime_str: str) -> int:
    try:
        dt = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
        return int(dt.timestamp())
    except ValueError:
        dt = dateparser.parse(datetime_str)
        if not dt:
            now = datetime.now().strftime("%Y/%m/%d %H:%M")
            raise ValueError(
                f"Invalid date/time format. Expected either:\n"
                f"• `YYYY/MM/DD HH:MM` (e.g. `{now}`)\n"
                f"• or natural language like `next week`, `tomorrow 18:00`, etc.\n\n"
                f"Got: `{datetime_str}`"
            )
        return int(dt.timestamp())


def to_discord_timestamp(dt: datetime, style: str = 'f') -> str:
    """Convert a datetime object to a Discord timestamp string."""
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


def star_rating(r: int) -> str:
    r = max(1, min(r, 5))
    return "★" * r + "☆" * (5 - r)


def get_embed_from_interaction(interaction: discord.Interaction) -> Optional[discord.Embed]:
    """
    Get the existing embed from the interaction message.

    Args:
        interaction: The Discord interaction

    Returns:
        The first embed if present, None otherwise
    """
    if interaction.message and interaction.message.embeds:
        return interaction.message.embeds[0]
    return None


def extract_ids_from_mentions(mentions_line: str, prefix: str = None) -> List[int]:
    """
    Extract user IDs from a line containing Discord mentions.

    Args:
        mentions_line: Line containing Discord user mentions
        prefix: Optional prefix to use

    Returns:
        List of extracted user IDs
    """
    mention_text = mentions_line.strip(prefix).strip()
    mention_tokens = mention_text.split()

    extracted_user_ids = []
    for token in mention_tokens:
        if token.startswith("<@") and token.endswith(">"):
            try:
                clean_id = token.strip("<@!>")
                user_id = int(clean_id)
                extracted_user_ids.append(user_id)
            except ValueError:
                continue

    return extracted_user_ids


def user_ids_to_mentions(
        users: Union[int, discord.User, discord.Member, Iterable[Union[int, discord.User, discord.Member]]]
) -> str:
    """
    Format user IDs or user objects into Discord mention strings.

    Args:
        users: A single user ID, user object, or an iterable of those.

    Returns:
        Space-separated string of user mentions.
    """
    if not isinstance(users, (list, set, tuple)):
        users = [users]

    mentions = []
    for user in users:
        if isinstance(user, int):
            user_id = user
        elif hasattr(user, "id"):
            user_id = user.id
        else:
            raise TypeError(f"Unsupported type {type(user)} in users input")

        mentions.append(f"<@{user_id}>")

    return " ".join(mentions)


def strip_surrounding_quotes(s):
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s