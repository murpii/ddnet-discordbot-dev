from typing import List, Optional, Tuple, TYPE_CHECKING

import discord

from constants import Guilds
from utils.containers import NoticeView, PagedLines
from utils.text import clip

if TYPE_CHECKING:
    from bot import DDNet

# Anything this long that is all digits is treated as an application ID
# instead of a game name (avoids eating game names like "2048").
SNOWFLAKE_MIN_LENGTH = 15


def playing_activities(member: discord.Member) -> list:
    """All "Playing ..." activities of a member (ignores Spotify, custom
    statuses, streaming and so on)."""
    return [
        activity for activity in member.activities
        if activity.type is discord.ActivityType.playing and activity.name  # noqa
    ]


def scan_guilds(bot: "DDNet") -> list:
    """All guilds, DDNet first: a user's presence is identical in every
    shared guild, so guild order decides which copy wins the dedup."""
    return sorted(bot.guilds, key=lambda guild: guild.id != Guilds.DDNET)


def iter_unique_members(bot: "DDNet"):
    """Every user the bot can see, once, across all guilds."""
    seen: set = set()
    for guild in scan_guilds(bot):
        for member in guild.members:
            if member.id in seen:
                continue
            seen.add(member.id)
            yield member


def collect_games(bot: "DDNet") -> dict:
    """Snapshot of everything currently being played across all guilds.
    Maps (game name, application ID or None) -> list of members."""
    games: dict[Tuple[str, Optional[int]], List[discord.Member]] = {}
    for member in iter_unique_members(bot):
        for activity in playing_activities(member):
            # .application_id only exists on rich activities, discord.Game
            # (plain detected/user-added games) doesn't even have the slot
            key = (activity.name, getattr(activity, "application_id", None))
            games.setdefault(key, []).append(member)
    return games


def find_players(bot: "DDNet", query: str) -> List[Tuple[discord.Member, discord.BaseActivity]]:
    """Members playing a specific game. A long all-digit query matches the
    application ID (exact, rich presence only); anything else matches the
    activity name case-insensitively as substring."""
    app_id = None
    if query.isdigit() and len(query) >= SNOWFLAKE_MIN_LENGTH:
        app_id = int(query)
    name_query = query.lower()

    matches = []
    for member in iter_unique_members(bot):
        for activity in playing_activities(member):
            if app_id is not None:
                found = getattr(activity, "application_id", None) == app_id
            else:
                found = name_query in activity.name.lower()
            if found:
                matches.append((member, activity))
                break  # one entry per member is enough
    return matches


def describe_player(member: discord.Member, activity) -> str:
    """One line per player; rich presence extras (e.g. DDNet's server/map
    info) are appended when the game reports them. Members of other guilds
    are shown by name (their mention wouldn't resolve on DDNet)."""
    if member.guild.id == Guilds.DDNET:
        line = f"{member.mention} › {clip(activity.name, 40)}"
    else:
        line = f"{member} › {clip(activity.name, 40)} (via {clip(member.guild.name, 30)})"

    extras = [
        clip(text, 60)
        for text in (getattr(activity, "details", None), getattr(activity, "state", None))
        if text
    ]
    if extras:
        line += f"\n-# {' | '.join(extras)}"
    return line


def build_playing_view(bot: "DDNet", game: str = None) -> discord.ui.LayoutView:
    """The complete "who is playing" response: an overview of all games when
    `game` is None or blank, otherwise the players of that game (name or
    app ID)."""
    game = (game or "").strip() or None  # blank input would match everyone
    if game is None:
        games = collect_games(bot)
        if not games:
            return NoticeView(
                "Nobody is playing anything visible right now.\n"
                "-# Offline/invisible members and members with the "
                "\"Display current activity\" privacy setting off are not counted."
            )

        ordered = sorted(games.items(), key=lambda kv: (-len(kv[1]), kv[0][0].lower()))
        lines = []
        for (name, app_id), members in ordered:
            line = f"`{clip(name, 40)}` -- {len(members)} playing"
            if app_id:
                line += f"\n-# app id: `{app_id}` (rich presence)"
            else:
                line += "\n-# no app id (auto-detected or user-added)"
            lines.append(line)

        title = f"Games being played: {len(ordered)}"
        if len(bot.guilds) > 1:
            title += f" (across {len(bot.guilds)} servers)"
        return PagedLines(title, lines)

    matches = find_players(bot, game)
    if not matches:
        return NoticeView(
            f'Nobody visible is playing "{clip(game, 60)}" right now.\n'
            "-# They may have stopped playing or gone offline in the meantime."
        )

    matches.sort(key=lambda pair: pair[0].display_name.lower())
    lines = [describe_player(member, activity) for member, activity in matches]
    return PagedLines(f"{len(matches)} member(s) playing {clip(game, 40)}", lines)
