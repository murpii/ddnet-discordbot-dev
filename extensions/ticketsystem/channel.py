import logging
from typing import Optional

import discord

from constants import Channels
from extensions.ticketsystem.mappings import START_CONTAINERS
from extensions.ticketsystem.ticket import Ticket, TicketCategory
from extensions.ticketsystem.utils import find_or_create_category
from extensions.ticketsystem.views.containers.close import CloseContainer
from utils.checks import check_dm_channel

log = logging.getLogger("tickets")


async def create_ticket_channel(
        interaction: discord.Interaction,
        ticket: Ticket,
) -> Optional[discord.TextChannel]:
    """Create just the Discord text channel for a ticket"""
    manager = interaction.client.ticket_manager

    if ticket.category == TicketCategory.COMMUNITY_APP:
        category = await manager.get_community_app_category(interaction.guild)
    else:
        category = interaction.guild.get_channel(Channels.CAT_TICKETS)

    target_category = await find_or_create_category(interaction.guild, category) if category else None
    if not target_category:
        await interaction.followup.send(
            "I could not create a ticket channel because all channel categories are full "
            "and I lack permissions to create a new one. Please contact a server administrator.",
            ephemeral=True,
        )
        return None

    ticket_name = f"{ticket.category.value}-{await manager.ticket_num(category=ticket.category.value)}"
    channel_params = {
        "name": ticket_name,
        "category": target_category,
        "overwrites": ticket.get_overwrites(interaction),
        "topic": manager.topic_metadata(ticket),
    }

    try:
        channel = await interaction.guild.create_text_channel(**channel_params)
        log.info(f"Successfully created ticket channel #{channel.name} ({channel.id})")
        return channel
    except discord.Forbidden:
        log.error(
            f"Failed to create ticket channel '{ticket_name}' in guild {interaction.guild.id}. "
            f"Bot lacks 'Manage Channels' permission."
        )
        await interaction.followup.send(
            "I do not have the required permissions to create a ticket channel. Please contact an administrator.",
            ephemeral=True,
        )
    except discord.HTTPException as e:
        log.error(f"An unexpected HTTP error occurred while creating channel '{ticket_name}': {e}")
        await interaction.followup.send(
            "An unexpected error occurred while creating your ticket. Please try again later.",
            ephemeral=True,
        )
    return None


async def build_ticket_channel(
        interaction: discord.Interaction,
        ticket: Ticket,
        *,
        init: bool = True,
        announce: bool = True,
) -> Optional[discord.TextChannel]:
    """Builds a complete ticket and post its start + close messages.

    Steps, in order:
      1. create the Discord channel (via create_ticket_channel)
      2. register the ticket in the manager (and, when ``init`` is True, the database)
      3. post the category's start container and the close container
      4. pin the start message
      5. when ``announce`` is True, confirm to the user with an ephemeral followup
    """
    manager = interaction.client.ticket_manager

    ticket.channel = await create_ticket_channel(interaction, ticket)
    if ticket.channel is None:
        return None

    await manager.create_ticket(ticket=ticket, channel=ticket.channel, init=init)

    start_container = START_CONTAINERS[ticket.category]
    ticket.start_message = await ticket.channel.send(view=start_container(ticket))  # noqa
    ticket.close_message = await ticket.channel.send(
        view=CloseContainer.for_category(ticket.category), allowed_mentions=discord.AllowedMentions(roles=False)
    )
    await ticket.start_message.pin()

    if announce:
        content = (
            f"<@{interaction.user.id}> your ticket has been created: "
            f"{ticket.start_message.jump_url}"
        )
        if not await check_dm_channel(interaction.user):
            content += (
                "\n\n**WARNING:**\n"
                "I wasn't able to send you a DM.\n"
                "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                "To fix this, shoot me a message or adjust your privacy settings."
            )
        await interaction.followup.send(content=content, ephemeral=True)

    log.info(
        f'{interaction.user} (ID: {interaction.user.id}) created a '
        f'"{ticket.category.value}" ticket (ID: {ticket.channel.id}).'
    )
    return ticket.channel
