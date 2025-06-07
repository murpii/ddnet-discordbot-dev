import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import groupby
import re

import discord
from discord import app_commands
from discord.ext import commands
from constants import Guilds, Roles, Channels


"""
    This script generates a poll featuring the best maps from a specified year.

    Instructions:
        1. Set the boolean for extensions.events.map_awards in bot.py to True.
        2. Use the `/load extension:map_awards` command to load this script.
           OR Restart the discord app & reload the discord webpage (CTRL+R) to see all the new app commands.
        4. Use the `/create_poll <year>` command to generate the selects for the poll.
        5. Wait 1 week
        6. Use the `/poll_results` to generate the results of the poll.
        7. Set the boolean for extensions.best_maps_poll in bot.py back to False.
        8.  Remove:
            - The poll discord channel
            - The user_selections.json in data/events/map-awards/
            - The all_maps.json in data/events/map-awards/
"""


ASSETS_DIR = "data/assets/map_backgrounds"
DATA_DIR = "data/events/map-awards"

log = logging.getLogger(__name__)

def predicate(interaction: discord.Interaction) -> bool:
    return Roles.ADMIN in [role.id for role in interaction.user.roles]


# taken from ddnet.py
def slugify2(name):
    x = "[\t !\"#$%&'()*-/<=>?@[\\]^_`{|},.:]+"
    string = ""
    for c in name:
        if c in x or ord(c) >= 128:
            string += "-%s-" % ord(c)
        else:
            string += c
    return string


def get_mapper_urls(maps_data, map_name):
    for map_info in maps_data:
        if map_info["Map"] == map_name:
            mappers = list(map_info["Mapper"].replace(" & ", ", ").split(", "))

            return [
                f"[{mapper}](https://ddnet.org/mappers/{slugify2(mapper)})"
                for mapper in mappers
            ]


class DDNetMapAwards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_selections = {}
        self.year = None

    order = [
        ("👶", "Novice"),
        ("🌸", "Moderate"),
        ("💪", "Brutal"),
        ("💀", "Insane"),
        ("♿", "Dummy"),
        ("👴", "Oldschool"),
        ("⚡", "Solo"),
        ("🏁", "Race"),
        ("🎉", "Fun"),
    ]

    async def fetch(self, query, *args):
        async with self.bot.pool.acquire() as connection:
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

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.check(predicate)
    @app_commands.command(name="map-awards", description="Use this command to create the poll with all the selects")
    @app_commands.describe(year="The map release year. Example: /create_poll year:2023")
    async def generate_poll_menu(self, interaction: discord.Interaction, year: int):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        self.year = year

        query = f"""
        SELECT * FROM record_maps 
        WHERE Timestamp BETWEEN '{year}-01-01' AND '{year + 1}-01-01' 
        ORDER BY Timestamp ASC;
        """

        records = await self.fetch(query)
        if not records:
            await interaction.followup.send("No records found.")
            return

        all_maps = {"year": year, "maps": {}}
        for record in records:
            server = record.get("Server")
            if server not in all_maps["maps"]:
                all_maps["maps"][server] = []
            all_maps["maps"][server].append(dict(record))

        with open(f"{DATA_DIR}/all_maps.json", "w", encoding="utf-8") as f:
            json.dump(all_maps, f, indent=2, default=str)

        views = []

        for emoji, server in self.order:
            if server in all_maps["maps"]:
                maps = all_maps["maps"][server]
                mapper = maps[0]["Mapper"]
                create_selects = CreateSelects(self.bot, server, maps, mapper)
                view = await create_selects.create_view()
                views.append(view)

        now = datetime.now(timezone.utc)
        future_time_utc = now + timedelta(days=7)
        unix_timestamp = int(future_time_utc.timestamp())

        category = interaction.guild.get_channel(Channels.CAT_INTERNAL)
        awards_channel = await category.create_text_channel("ddnet-awards-poll")

        await awards_channel.send(
            f"# Which map did you enjoy the most in {self.year}? \n"
            "Make your selections down below! Only **one map per server difficulty can be selected**, so choose wisely."
            f"\nThe poll will run for **1 week** and will end on **<t:{unix_timestamp}:F>**"
        )

        for view, (emoji, server) in zip(views, self.order):
            await awards_channel.send(content=f"## {emoji} {server}:", view=view)

        await interaction.followup.send(
            content=f"Poll sent in {awards_channel.mention}", ephemeral=True
        )

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.check(predicate)
    @app_commands.command(name="poll_results", description="Use this command to post the poll results.")
    async def poll_results(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        with open(f"{DATA_DIR}/user_selections.json", "r") as file:
            user_selections = json.load(file)

        with open(f"{DATA_DIR}/all_maps.json", "r") as file:
            all_maps = json.load(file)

        category_counts = {}
        for user_id, categories in user_selections.items():
            for category, maps in categories.items():
                category_counts.setdefault(category, Counter())[maps[0]] += 1

        sorted_categories = sorted(
            category_counts.keys(), key=lambda x: next(i for i, (_, cat) in enumerate(self.order) if cat == x)
        )

        category = interaction.guild.get_channel(Channels.CAT_INTERNAL)
        awards_channel = await category.create_text_channel(f"ddnet-awards-{self.year}")

        await awards_channel.send(f"# DDNet Map Awards {self.year}:")

        for category in sorted_categories:
            counter = category_counts[category]
            sorted_counter = sorted(counter.items(), key=lambda x: x[1], reverse=True)
            grouped_counter = [
                list(group)
                for key, group in groupby(sorted_counter, key=lambda x: x[1])
            ]

            emoji = next(emoji for emoji, cat in self.order if cat == category)

            message = f"## {emoji} {category}: \n"

            for rank, group in enumerate(grouped_counter[:3], start=1):
                ranks = []

                for map_name, votes in group:
                    mappers = get_mapper_urls(all_maps["maps"][category], map_name)
                    ranks.append(
                        f"**[{map_name}](https://ddnet.org/maps/{slugify2(map_name)})** "
                        f"— Mapper(s): {', '.join(mappers)}"
                    )

                map_names = " | ".join(ranks)
                message += f"{rank}. {map_names} **with {group[0][1]} votes**\n"

            message += "\n"
            await awards_channel.send(message)

        await interaction.followup.send(
            content=f"Poll results sent in: {awards_channel.mention}", ephemeral=True
        )

    @commands.Cog.listener('on_ready')
    async def load_poll_data(self):
        try:
            with open(f"{DATA_DIR}/all_maps.json", "r", encoding="utf-8") as json_file:
                all_maps = json.load(json_file)
        except FileNotFoundError:
            log.error(
                "Map awards module loaded, but poll data files are missing. "
                "Files are generated via /create_poll command."
            )
            return

        self.year = all_maps["year"]

        views = []
        for server, maps in all_maps["maps"].items():
            mapper = maps[0]["Mapper"]
            create_selects = CreateSelects(self.bot, server, maps, mapper)
            view = await create_selects.create_view()
            views.append(view)

        for view in views:
            self.bot.add_view(view=view)


class CreateSelects(discord.ui.View):
    def __init__(self, bot, server, maps, mapper):
        self.bot = bot
        self.server = server
        self.maps = maps
        self.user_selections = {}
        self.mapper = mapper
        super().__init__(timeout=None)

    async def interaction_callback(self, interaction: discord.Interaction):
        try:
            with open(f"{DATA_DIR}/user_selections.json", "r", encoding="utf-8") as f:
                self.user_selections = json.load(f)
        except FileNotFoundError:
            self.user_selections = {}
            with open(f"{DATA_DIR}/user_selections.json", "w+", encoding="utf-8") as f:
                json.dump(self.user_selections, f)

        user_id = str(interaction.user.id)

        if user_id not in self.user_selections:
            self.user_selections[user_id] = {}

        custom_id = interaction.data["custom_id"]
        custom_id_parts = custom_id.split("_")
        server = custom_id_parts[1]
        selected_map = interaction.data["values"][0].split(" by ")[0]

        if server not in self.user_selections[user_id]:
            self.user_selections[user_id][server] = []

        old_selection = self.user_selections[user_id][server]

        try:
            file = discord.File(
                f"{ASSETS_DIR}/{selected_map}.png", filename=f"map_{selected_map}.png"
            )
        except FileNotFoundError:
            # Attempt to load the file with underscores instead of spaces
            corrected_map = re.sub(r'[^a-zA-Z0-9]', '_', selected_map)
            file = discord.File(
                f"{ASSETS_DIR}/{corrected_map}.png", filename=f"map_{corrected_map}.png"
            )

        if old_selection:
            old_selection = old_selection[0]
            self.user_selections[user_id][server] = [selected_map]

            await interaction.response.send_message(  # noqa
                f"## {server} Server: \n"
                f"Replaced your old selection: [{old_selection}](https://ddnet.org/maps/{slugify2(old_selection)}) "
                f"with map: [{selected_map}](https://ddnet.org/maps/{slugify2(selected_map)})",
                ephemeral=True,
                file=file,
            )
        else:
            self.user_selections[user_id][server].append(selected_map)

            await interaction.response.send_message(  # noqa
                f"## {server} Server: \n"
                f"Map [{selected_map}](https://ddnet.org/maps/{slugify2(selected_map)}) selected.",
                ephemeral=True,
                file=file,
            )

        with open(
            f"{DATA_DIR}/user_selections.json", "w", encoding="utf-8"
        ) as json_file:
            json.dump(self.user_selections, json_file, indent=2)

    async def create_view(self):
        options = sorted(
            [
                discord.SelectOption(
                    label=f"{map_data['Map']} by {map_data['Mapper']}",
                    value=map_data["Map"],
                )
                for map_data in self.maps
            ],
            key=lambda x: x.label,
        )

        options = [options[i : i + 25] for i in range(0, len(options), 25)]

        for i, chunk in enumerate(options):
            option_desc = f"Select a map on {self.server} server"
            if len(options) > 1:
                option_desc += f" (Page {i + 1})"
            custom_id = f"select_{self.server}_{i}"
            select_menu = discord.ui.Select(custom_id=custom_id, options=chunk, placeholder=option_desc)
            select_menu.callback = self.interaction_callback
            self.add_item(select_menu)

        return self


async def setup(bot):
    await bot.add_cog(DDNetMapAwards(bot))
