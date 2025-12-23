import aiohttp
import logging
import discord
import re

from utils.misc import get_filename_from_header

log = logging.getLogger(__name__)


async def find_or_create_category(
        guild: discord.Guild,
        category: discord.CategoryChannel
) -> discord.CategoryChannel | None:
    """
    Finds an available category or creates a new one
    A category is considered available if it has fewer than 50 channels
    This function will search for categories with the same name as the base_category first
    """
    if len(category.channels) < 50:
        return category

    try:
        position = category.position + 1 if category else 0
        return await guild.create_category(name=category.name, position=position)
    except discord.Forbidden:
        log.error(f"Failed to create new ticket category in guild {guild.id}. Bot lacks 'Manage Channels' permission.")
        return None
    except discord.HTTPException as e:
        log.error(f"An HTTP error occurred while creating a category in guild {guild.id}: {e}")
        return None


async def fetch_rank_from_demo(bot, message: discord.Message, session: aiohttp.ClientSession):
    demo_names = []
    for attachment in message.attachments:
        if attachment.filename.endswith(".demo"):
            filename = await get_filename_from_header(session, url=attachment.url)
            demo_names.append(filename)

    ranks = []

    for demo in demo_names:
        match = re.match(r"(.+?)_(\d+\.\d+)_([^.]+(?:\.+)*)\.demo", demo)
        if not match:
            continue

        map_name, time_str, player_name = match.groups()
        print(player_name)
        if '.' in time_str:
            time_str = time_str.rstrip('0').rstrip('.')

        map_name = f"%{map_name}%"
        query = """
                SELECT Timestamp
                FROM record_race
                WHERE Map LIKE %s
                  AND Time LIKE %s
                  AND Name = %s \
                """
        result = await bot.fetch(query, map_name, time_str, player_name, fetchall=False)

        if result:
            timestamp = result[0]
            ranks.append((demo, timestamp))

    return ranks
