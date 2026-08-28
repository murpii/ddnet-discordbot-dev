import json

from extensions.map_awards.map_awards import CreateSelects, DDNetMapAwards

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


async def setup(bot: "DDNet"):
    await bot.add_cog(DDNetMapAwards(bot))

    servers = ["Novice", "Moderate", "Brutal", "Insane", "Dummy", "Oldschool", "Solo", "Race", "Fun"]
    for server in servers:
        with open("data/events/map-awards/all_maps.json", "r", encoding="utf-8") as f:
            all_maps = json.load(f)

        if server not in all_maps["maps"]:
            continue

        view = await CreateSelects(
            bot,
            server,
            all_maps["maps"][server],
            all_maps["maps"][server][0]["Mapper"]
        ).create_view()

        bot.add_view(view=view)
