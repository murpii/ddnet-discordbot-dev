import asyncio
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import groupby
from math import ceil
from typing import TYPE_CHECKING

import discord
from discord import PermissionOverwrite, app_commands
from discord.ext import commands

from constants import Emojis, Guilds
from extensions.map_awards import queries
from extensions.map_awards.container import CategoryResultsView, StatsResultsView
from utils.checks import staff_only
from utils.misc import get_mapper_urls
from utils.text import slugify2

if TYPE_CHECKING:
    from bot import DDNet

ASSETS_DIR = "data/assets/map_backgrounds"
DATA_DIR = "data/events/map-awards"
file_lock = asyncio.Lock()

log = logging.getLogger(__name__)


class DDNetMapAwards(commands.Cog):
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

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.year = None

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @staff_only("admins")
    @app_commands.command(name="map-awards")
    async def generate_poll_menu(self, interaction: discord.Interaction, year: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        self.year = year

        await interaction.edit_original_response(content="⏳ Fetching map records...")
        records = await self.fetch_map_records(year)
        all_maps = self.build_all_maps(year, records)

        await interaction.edit_original_response(
            content="📊 Calculating finishes... (This may take awhile!)"
        )

        # Standard stats
        stats = await self.fetch_stats(year)

        # Additional yearly stats (stored, not printed here)
        top_maps = await self.bot.fetch(
            queries.top_5_most_finished_maps(year), fetchall=True
        )
        top_player = await self.bot.fetch(
            queries.top_player_of_the_year(), fetchall=True
        )

        stats.update(
            {
                "top_5_maps": top_maps,
                "top_player": top_player[0] if top_player else None,
            }
        )

        all_maps["stats"] = stats

        with open(f"{DATA_DIR}/all_maps.json", "w", encoding="utf-8") as f:
            json.dump(all_maps, f, indent=2, default=str)

        await interaction.edit_original_response(
            content="📁 Creating category and channels..."
        )
        await self.create_poll_channels(interaction, all_maps)

    async def fetch_map_records(self, year: int) -> list[dict]:
        raw_records = await self.bot.fetch(
            queries.maps_released_in_year(year), fetchall=True
        )

        columns = ("Map", "Server", "Points", "Stars", "Mapper", "Timestamp")
        return [dict(zip(columns, row)) for row in raw_records]

    @staticmethod
    def build_all_maps(year: int, records: list[dict]) -> dict:
        all_maps = {"year": year, "stats": {}, "maps": {}}
        for record in records:
            all_maps["maps"].setdefault(record["Server"], []).append(record)
        return all_maps

    async def fetch_stats(self, year: int) -> dict:
        nonfun = await self.bot.fetch(queries.total_finishes_nonfun(year))
        total = await self.bot.fetch(queries.total_finishes_all(year))
        return {
            "total_finishes_nonfun": nonfun[0] if nonfun else 0,
            "total_finishes_all": total[0] if total else 0,
        }

    async def create_poll_channels(self, interaction, all_maps):
        future = datetime.now(timezone.utc) + timedelta(days=7)
        unix = ceil(future.timestamp() / 3600) * 3600

        overwrites = {
            interaction.guild.default_role: PermissionOverwrite(view_channel=False),
            interaction.guild.me: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }

        cat = await interaction.guild.create_category(
            f"Mapper Awards {self.year}", overwrites=overwrites
        )

        channel = await cat.create_text_channel("ddnet-awards-poll")

        await channel.send(
            f"# <:ddnet:{Emojis.DDNET}> Which map did you enjoy the most in {self.year}?\n\n"
            f"Make your selections down below! Only **one map per difficulty can be selected**, so choose wisely.\n"
            f"Poll ends **<t:{unix}:F>**\n\n"
        )

        for emoji, server in self.order:
            if server not in all_maps["maps"]:
                continue

            view = await CreateSelects(
                self.bot,
                server,
                all_maps["maps"][server],
                all_maps["maps"][server][0]["Mapper"],
            ).create_view()

            await channel.send(f"## {emoji} {server}", view=view)

        await interaction.edit_original_response(
            content=f"✅ Poll created successfully: {channel.mention}!"
        )

    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @staff_only("admins")
    @app_commands.command(name="poll_results")
    async def poll_results(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        with open(f"{DATA_DIR}/user_selections.json", encoding="utf-8") as f:
            selections = json.load(f)

        with open(f"{DATA_DIR}/all_maps.json", encoding="utf-8") as f:
            all_maps = json.load(f)

        counts: dict[str, Counter] = {}

        for user in selections.values():
            for category, maps in user.items():
                if not maps:
                    continue

                if selected_map := maps[0]:
                    counts.setdefault(category, Counter())[selected_map] += 1

        category_name = f"Mapper Awards {all_maps['year']}"
        category = discord.utils.get(
            interaction.guild.categories,
            name=category_name,
        )

        if category is None:
            await interaction.followup.send(
                f"Error: category '{category_name}' not found.",
                ephemeral=True,
            )
            return

        overwrites = {
            interaction.guild.default_role: PermissionOverwrite(view_channel=False),
            interaction.guild.me: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
            ),
        }

        channel = await category.create_text_channel(
            f"ddnet-awards-{all_maps['year']}",
            overwrites=overwrites,
        )

        await channel.send(
            f"# 🗺️ DDNet Map Awards For {all_maps['year']}\n"
            "Congratulations to all mappers! Results per category below."
        )

        # PER-CATEGORY RESULTS
        for category, counter in counts.items():
            valid_entries = [(m, v) for m, v in counter.items() if v > 0]
            if not valid_entries:
                continue

            emoji = next(e for e, c in self.order if c == category)

            text, media_items, files = self.format_category(
                category,
                emoji,
                Counter(dict(valid_entries)),
                all_maps,
            )

            view = CategoryResultsView(
                text=text,
                media_items=media_items,
            )

            await channel.send(view=view, files=files)

        # STATS VIEW
        stats = all_maps["stats"]

        top_maps_str = ""
        if stats.get("top_5_maps"):
            top_maps_str = "\n".join(
                f"> {i + 1}. {map_name} — **{finishes:,} finishes**"
                for i, (map_name, finishes) in enumerate(stats["top_5_maps"])
            )

        top_player_str = ""
        if stats.get("top_player"):
            player, points = stats["top_player"]
            top_player_str = f"**{player}** — {points:,} points"

        stats_text = (
            "## 📊 General Statistics\n"
            f"Finishes (all): **{stats['total_finishes_all']:,}**\n"
            f"Finishes (Excl. Fun): **{stats['total_finishes_nonfun']:,}**\n"
            "-# Included maps: Castle Echos, KingsLeap, Linear II, Good Movement, "
            "IWannaBeatTheMap, IWannaBeatTheMap2, MultiFAT, Flappy Bird, Edge Jump Pro\n\n"
            "### 🏆 Top 5 Most Finished Maps\n"
            f"{top_maps_str or 'No data available'}\n"
        )

        await channel.send(view=StatsResultsView(stats_text))

        await interaction.followup.send(
            f"Poll results posted in {channel.mention}",
            ephemeral=True,
        )

    @staticmethod
    def format_category(category, emoji, counter, all_maps):
        grouped = groupby(
            sorted(counter.items(), key=lambda x: x[1], reverse=True),
            key=lambda x: x[1],
        )

        text = f"## {emoji} {category}\n"
        media_items = []
        files = []

        TROPHIES = ["🥇", "🥈", "🥉"]

        for rank, (votes, group) in enumerate(grouped, start=1):
            if rank > 3:
                break

            if votes <= 0:
                continue

            entries = []
            for map_name, _ in list(group):
                mappers = get_mapper_urls(
                    all_maps["maps"][category],
                    map_name,
                )

                entries.append(
                    f"**[{map_name}](https://ddnet.org/maps/{slugify2(map_name)})** "
                    f"— {', '.join(mappers)}"
                )

                if rank == 1 and not media_items:
                    try:
                        file = discord.File(
                            f"{ASSETS_DIR}/{map_name}.png",
                            filename=f"map_{map_name}.png",
                        )
                    except FileNotFoundError:
                        safe = re.sub(r"[^a-zA-Z0-9]", "_", map_name)
                        file = discord.File(
                            f"{ASSETS_DIR}/{safe}.png",
                            filename=f"map_{safe}.png",
                        )

                    files.append(file)
                    media_items.append(
                        discord.MediaGalleryItem(
                            f"attachment://{file.filename}"
                        )
                    )

            text += f"{TROPHIES[rank - 1]} {' | '.join(entries)} (**{votes} votes**)\n"

        return text, media_items, files


class CreateSelects(discord.ui.View):
    def __init__(self, bot: "DDNet", server, maps, mapper):
        self.bot = bot
        self.server = server
        self.maps = maps
        self.user_selections = {}
        self.mapper = mapper
        super().__init__(timeout=None)

    async def interaction_callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        custom_id = interaction.data["custom_id"]
        custom_id_parts = custom_id.split("_")
        server = custom_id_parts[1]

        selected_map = interaction.data["values"][0].split(" by ")[0]

        async with file_lock:
            try:
                with open(f"{DATA_DIR}/user_selections.json", "r", encoding="utf-8") as f:
                    self.user_selections = json.load(f)
            except FileNotFoundError:
                self.user_selections = {}

            if user_id not in self.user_selections:
                self.user_selections[user_id] = {}
            if server not in self.user_selections[user_id]:
                self.user_selections[user_id][server] = []

            if old_selection := self.user_selections[user_id][server]:
                old_map = old_selection[0]
                self.user_selections[user_id][server] = [selected_map]
                replaced = True
            else:
                self.user_selections[user_id][server].append(selected_map)
                replaced = False

            # Save back to file
            with open(f"{DATA_DIR}/user_selections.json", "w", encoding="utf-8") as json_file:
                json.dump(self.user_selections, json_file, indent=2)

        try:
            file = discord.File(
                f"{ASSETS_DIR}/{selected_map}.png",
                filename=f"map_{selected_map}.png",
            )
        except FileNotFoundError:
            safe_name = re.sub(r"[^a-zA-Z0-9]", "_", selected_map)
            file = discord.File(
                f"{ASSETS_DIR}/{safe_name}.png",
                filename=f"map_{safe_name}.png",
            )

        if replaced:
            await interaction.response.send_message(
                f"## {server} Server:\n"
                f"Replaced your old selection: "
                f"[{old_map}](https://ddnet.org/maps/{slugify2(old_map)}) "
                f"with map: "
                f"[{selected_map}](https://ddnet.org/maps/{slugify2(selected_map)})",
                ephemeral=True,
                file=file,
            )
        else:
            await interaction.response.send_message(
                f"## {server} Server:\n"
                f"Map "
                f"[{selected_map}](https://ddnet.org/maps/{slugify2(selected_map)}) "
                f"selected.",
                ephemeral=True,
                file=file,
            )

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

        options_chunks = [options[i:i + 25] for i in range(0, len(options), 25)]

        for i, chunk in enumerate(options_chunks):
            option_desc = f"Select a map on {self.server} server"
            if len(options_chunks) > 1:
                option_desc += f" (Page {i + 1})"

            custom_id = f"select_{self.server}_{i}"
            select_menu = discord.ui.Select(
                custom_id=custom_id,
                options=chunk,
                placeholder=option_desc,
            )
            select_menu.callback = self.interaction_callback
            self.add_item(select_menu)

        return self
