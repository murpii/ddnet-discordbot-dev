import datetime as dtt
from datetime import datetime
from requests import ReadTimeout
import discord
from discord import app_commands
from discord.ext import commands

from utils.image import (
    generate_profile_image,
    generate_hours_image,
    generate_map_image,
    generate_points_image,
)
from utils.text import escape_backticks, human_timedelta

tiles_filter = [
    "EHOOK_START",
    "HIT_END",
    "JETPACK_START",
    "NPC_START",
    "POWERUP_NINJA",
    "SOLO_START",
    "SUPER_START",
    "WALLJUMP",
    "WEAPON_GRENADE",
    "WEAPON_RIFLE",
    "WEAPON_SHOTGUN",
]


async def fetch_db(pool, query, *args):
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, args)
            rows = await cursor.fetchall()
            if not rows:
                return None
            column_names = [desc[0] for desc in cursor.description]
            return [
                {column_names[i]: row[i] for i in range(len(column_names))}
                for row in rows
            ]


# noinspection PyTypeChecker
class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def source(self, url, timeout: int = 20):
        try:
            resp = self.bot.request_cache.get(url, timeout=timeout)
            return resp.json() if resp.status_code == 200 else None
        except ReadTimeout:
            return None

    async def map_autocomplete(
        self, _: discord.Interaction, name: str
    ) -> list[app_commands.Choice[str]]:
        query = """SELECT map FROM record_maps WHERE map LIKE %s LIMIT 12;"""
        w = f"%{name}%"
        results: list[str] = await self.bot.fetch(query, w, fetchall=True)
        return [app_commands.Choice(name=a, value=a) for a, in results]

    # Unsure if this is a good idea to use autocomplete for profiles
    async def profile_autocomplete(
        self, _: discord.Interaction, name: str
    ) -> list[app_commands.Choice[str]]:
        query = """SELECT DISTINCT name FROM record_race WHERE name LIKE %s LIMIT 12;"""
        w = f"%{name}%"
        results: list[str] = await self.bot.fetch(query, w, fetchall=True)
        return [app_commands.Choice(name=a, value=a) for a, in results]

    @app_commands.command(
        name="profile",
        description="Shows details about a player, including total points, favorite server, and other information.")
    @app_commands.describe(
        player="Enter the player name for which you'd like to view the details.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    @app_commands.autocomplete(player=profile_autocomplete)
    async def profile(self, interaction: discord.Interaction, player: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        player = player or interaction.user.display_name
        json_data = self.source(f"https://ddnet.org/players/?json2={player}", 10)

        if not json_data:
            await interaction.followup.send(content=f"`{player}` does not exist.")
            return

        profile = {
            "name": json_data["player"],
            "total_points": json_data["points"],
            "team_rank": {
                "rank": json_data["team_rank"].get("rank", None),
                "points": json_data["team_rank"].get("points", None),
            },
            "rank": {
                "rank": json_data["rank"].get("rank", None),
                "points": json_data["rank"].get("points", None),
            },
            "favorite_server": json_data["favorite_server"],
            "day": datetime.fromtimestamp(json_data["first_finish"]["timestamp"]).day,
            "month": datetime.fromtimestamp(
                json_data["first_finish"]["timestamp"]
            ).month,
        }

        buf = await generate_profile_image(profile)
        file = discord.File(buf, filename=f"profile_{player}.png")
        await interaction.followup.send(file=file)

    @app_commands.command(name="points", description="Shows or compares points of the provided player(s)")
    @app_commands.describe(
        players="Optional: You can query multiple players by separating each player with a comma.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def points(self, interaction: discord.Interaction, players: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        players = (
            [player.strip() for player in players.split(",") if players is not None]
            if players
            else [interaction.user.display_name]
        )

        data = {}
        not_found = []

        for player in players:
            if player in data:
                continue

            json_data = self.source(f"https://ddnet.org/players/?json2={player}", 5)

            if json_data is not None:
                try:
                    player = json_data["player"]
                    data[player] = []
                except KeyError:
                    not_found.append(player)
                    continue

                for difficulty, difficulty_data in json_data["types"].items():
                    if "maps" in difficulty_data:
                        for map_name, map_data in difficulty_data["maps"].items():
                            if "first_finish" in map_data:
                                first_finish_date = dtt.datetime.fromtimestamp(
                                    map_data["first_finish"]
                                ).date()
                                points = map_data["points"]
                                data[player].append((first_finish_date, points))

            if json_data is None:  # queries all the relevant data from our mariadb as fallback
                query = """
                    SELECT rr.Name, rr.Timestamp, rm.Points
                    FROM record_race rr
                    JOIN record_maps rm ON rr.Map = rm.Map
                    WHERE rr.Name = %s
                    AND (rr.Map, rr.Timestamp) IN
                    (SELECT rr.Map, MIN(rr.Timestamp)
                    FROM record_race rr
                    WHERE rr.Name = %s
                    GROUP BY rr.Map)
                    AND rm.Points > 0
                    ORDER BY rr.Timestamp;
                    """

                records = await fetch_db(self.bot.pool, query, player, player)

                if not records:
                    not_found.append(player)
                    continue

                for entry in records:
                    name = entry["Name"]
                    date = entry["Timestamp"].date()
                    points = entry["Points"]
                    if name not in data:
                        data[name] = []
                    data[name].append((date, points))

        for player, records in data.items():
            data[player] = sorted(records, key=lambda x: x[0])

        if not data:
            msg = "No data found for given player(s)."
            await interaction.followup.send(content=msg)
            return

        buf = await generate_points_image(data)
        file = discord.File(buf, filename=f'points_{"_".join(players)}.png')

        if not_found:
            msg = f"Could not find player(s): {'`' + '`, `'.join(not_found) + '`'}"
            await interaction.followup.send(content=msg, file=file)
        else:
            await interaction.followup.send(file=file)

    @app_commands.command(
        name="map",
        description="Shows map details, such as total finishes, difficulty, points, the map release date and the top10")
    @app_commands.describe(
        name="Enter the map name for which you'd like to view the details.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    @app_commands.autocomplete(name=map_autocomplete)
    async def map(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        json_data = self.source(f"https://ddnet.org/maps/?json={name}", 60)
        result = {}

        if json_data:
            result = {
                "name": json_data["name"],
                "mappers": json_data["mapper"],
                "finishers": json_data["finishers"],
                "server": json_data["type"],
                "points": json_data["points"],
                "tiles": [
                    value for value in json_data["tiles"] if value in tiles_filter
                ],
            }

            release_timestamp = json_data.get("release")
            if release_timestamp is not None and release_timestamp != "UNKNOWN":
                release_timestamp = int(release_timestamp)
                timestamp = dtt.datetime.fromtimestamp(release_timestamp)
            else:
                timestamp = "UNKNOWN"
            result["timestamp"] = timestamp

            ranks = json_data["ranks"][:10]
            result["ranks"] = [
                (entry["player"], int(entry["rank"]), float(entry["time"]))
                for entry in ranks
            ]

        if (
            json_data is None
        ):  # queries all the relevant data from our mariadb as fallback
            map_info = """
            SELECT rm.*, rmi.*, finishers
            FROM record_maps rm
            JOIN record_mapinfo rmi ON rm.Map = rmi.Map
            JOIN (
                SELECT COUNT(DISTINCT Name) AS finishers
                FROM record_race
                WHERE Map = %s
            ) AS race_stats
            WHERE rm.Map = %s;
            """

            record_race = """
            SELECT l.Name, mintime
            FROM(
                SELECT * FROM record_race WHERE Map = %s
            ) AS l
            JOIN(
                SELECT Name, MIN(Time) AS mintime
                FROM record_race WHERE Map = %s
                GROUP BY Name
                ORDER BY mintime ASC LIMIT 10
            ) AS r
            ON l.Time = r.mintime AND l.Name = r.Name
            GROUP BY Name
            ORDER BY mintime, l.Name;
            """

            map_info = await fetch_db(self.bot.pool, map_info, name, name)

            if map_info:
                for entry in map_info:
                    result = {
                        "name": entry["Map"],
                        "timestamp": (
                            entry["Timestamp"]
                            if entry["Timestamp"] != "0000-00-00 00:00:00"
                            else "UNKNOWN"
                        ),
                        "mappers": entry["Mapper"],
                        "server": entry["Server"],
                        "points": entry["Points"],
                        "finishers": entry["finishers"],
                        "tiles": [
                            key
                            for key, value in entry.items()
                            if value != 0 and key in tiles_filter
                        ],
                    }

                record_race = await fetch_db(
                    self.bot.pool, record_race, name, name
                )

                ranks = []
                previous_time = None
                rank = 1

                for record in record_race:
                    time = record["mintime"]
                    if time != previous_time:
                        rank = len(ranks) + 1
                        previous_time = time
                    ranks.append((record["Name"], rank, time))
                result["ranks"] = ranks

        if not result:
            await interaction.followup.send(f"Could not find `{name}`.")
            return

        buf = await generate_map_image(result)
        file = discord.File(buf, filename=f"map_{name}.png")
        await interaction.followup.send(file=file)

    @app_commands.command(
        name="activity",
        description="Display activity for up to 5 players based on finishes/hour.UTC +0. Green marks the current hour.")
    @app_commands.describe(
        players="Optional: You can query multiple players by separating each player with a comma.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def activity(self, interaction: discord.Interaction, players: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        players = (
            [player.strip() for player in players.split(",") if players is not None]
            if players
            else [interaction.user.display_name]
        )

        query = """
        SELECT name, EXTRACT(HOUR FROM timestamp) AS hour, COUNT(*) AS finishes
        FROM record_race
        WHERE Name = %s
        GROUP BY name, hour;
        """

        data = {}
        not_found = []

        for player in players:
            if player in data:
                continue

            records = await fetch_db(self.bot.pool, query, player)

            if not records:
                not_found.append(player)
                continue

            for item in records:
                name = item["name"]
                hour_finishes = (item["hour"], item["finishes"])
                if name not in data:
                    data[name] = []
                data[name].append(hour_finishes)

        if not data:
            msg = "No activity found for given player(s)."
            await interaction.followup.send(content=msg)
            return

        buf = await generate_hours_image(data)
        file = discord.File(buf, filename=f'hours_{"_".join(players)}.png')

        if not_found:
            msg = f"Could not find player(s): {'`' + '`, `'.join(not_found) + '`'}"
            await interaction.followup.send(content=msg, file=file)
        else:
            await interaction.followup.send(file=file)

    @app_commands.command(
        name="total_time",
        description="Display the total time of all finishes by a player")
    @app_commands.describe(
        player="Enter the player name for which you'd like to view the total time.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    @app_commands.autocomplete(player=profile_autocomplete)
    async def total_time(self, interaction: discord.Interaction, player: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        player = player or interaction.user.display_name

        query = "SELECT SUM(time) AS Time FROM record_race WHERE Name = %s;"
        time = await fetch_db(self.bot.pool, query, player)

        if time[0]['Time'] is None:
            await interaction.followup.send("Could not find that player.")
            return

        time = human_timedelta(time[0]["Time"])
        await interaction.followup.send(
            f"Total time (The sum of all finishes combined) for ``{escape_backticks(player)}``: **{time}**"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
