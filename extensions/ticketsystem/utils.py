import aiohttp
import discord
import re

from constants import Channels
from extensions.ticketsystem.manager import Ticket
from utils.misc import get_filename_from_header


async def create_ticket_channel(interaction: discord.Interaction, ticket: Ticket, ticket_manager):
    default_category = interaction.guild.get_channel(Channels.CAT_TICKETS)
    ticket_name = f"{ticket.category.value}-{await ticket_manager.ticket_num(category=ticket.category.value)}"

    try:
        return await interaction.guild.create_text_channel(
            name=ticket_name,
            category=default_category,
            overwrites=ticket.get_overwrites(interaction),
            topic=f"Ticket author: <@{interaction.user.id}>",
        )
    except discord.errors.HTTPException as e:
        if e.code == 50035:
            ticket_category = None
            for category in interaction.guild.categories:
                if category.name == "Tickets" and len(category.channels) < 50:
                    ticket_category = category
                    break

            if ticket_category is None:
                ticket_category = await interaction.guild.create_category(
                    name="Tickets", 
                    position=default_category.position
                )

            return await interaction.guild.create_text_channel(
                name=ticket_name,
                category=ticket_category,
                overwrites=ticket.get_overwrites(interaction),
                topic=f"Ticket author: <@{interaction.user.id}>",
            )
        else:
            return await interaction.followup.send(f"An unexpected error occurred: {e}")


async def fetch_rank_from_demo(bot, message: discord.Message, session: aiohttp.ClientSession):
    demo_names = []
    for attachment in message.attachments:
        if attachment.filename.endswith(".demo"):
            filename = await get_filename_from_header(session, url=attachment.url)
            demo_names.append(filename)
    
    ranks = []

    for demo in demo_names:
        match = re.match(r"(.+?)_(\d+\.\d+)_([^.]+(?:\.[^.]+)*)\.demo", demo)
        if not match:
            continue

        map_name, time_str, player_name = match.groups()
        if '.' in time_str:
            time_str = time_str.rstrip('0').rstrip('.')

        map_name = f"%{map_name}%"
        query = """
        SELECT Timestamp FROM record_race
        WHERE Map LIKE %s
        AND Time LIKE %s
        AND Name = %s
        """
        result = await bot.fetch(query, map_name, time_str, player_name, fetchall=False)

        if result:
            timestamp = result[0]
            ranks.append((demo, timestamp))
    
    return ranks