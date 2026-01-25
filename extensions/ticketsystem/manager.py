import asyncio
import contextlib
import logging
import re
from typing import Optional
import discord
from discord.ext import commands

import extensions.ticketsystem.queries as queries
from constants import Guilds, Channels
from utils.profile import PlayerProfile
from . import embeds
from .ticket import Ticket, AppealData, TicketCategory, TicketState, RenameData
from .utils import find_or_create_category
from .views.containers.admin_mail import AdminMailContainer
from .views.containers.ban_appeal import BanAppealContainer
from .views.containers.community_app import CommunityAppContainer
from .views.containers.complaint import ComplaintContainer
from .views.containers.rename import RenameContainer
from .views.containers.report import ReportContainer

log = logging.getLogger("tickets")


class TicketManager:
    """Manage the lifecycle of tickets within our Discord server.

    Attributes:
        tickets (dict): A dictionary mapping channel IDs to their corresponding ticket objects.
        lock (asyncio.Lock): A lock to manage concurrent access to ticket operations.
    """

    def __init__(self, bot):
        self.bot = bot
        self.tickets = {}
        self.lock = asyncio.Lock()
        self.cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, lambda i: i.user.id)

    def dump(self):
        return {
            cid: {
                "channel": f"{ticket.channel.name}",
                "category": ticket.category.value,
                "state": ticket.state.value or "unclaimed",
                "locked": ticket.locked,
                "being_closed": ticket.being_closed,
                "rename_data": (
                    {
                        "old_name": ticket.rename_data.old_profile.name,
                        "new_name": ticket.rename_data.new_profile.name,
                    }
                    if ticket.rename_data
                    else None
                ),
                "appeal_data": (
                    {
                        "name": ticket.appeal_data.name,
                        "address": ticket.appeal_data.address,
                        "dnsbl": ticket.appeal_data.dnsbl,
                        "reason": ticket.appeal_data.reason,
                        "appeal": ticket.appeal_data.appeal,
                    }
                    if ticket.appeal_data
                    else None
                ),
            }
            for cid, ticket in self.tickets.items()
        }

    @staticmethod
    def parse_ticket_topic(topic: str) -> dict[str, str]:
        """Parse a ticket topic into a dictionary of fields."""
        data = {}
        for line in topic.splitlines():
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
        print(data)
        return data

    async def create_channel(self, interaction: discord.Interaction, ticket: Ticket):
        """
        Creates a new ticket channel in an appropriate category.
        Uses the channel topic to store ticket metadata (author, category, etc.).
        """
        category = interaction.guild.get_channel(Channels.CAT_TICKETS)
        target_category = await find_or_create_category(interaction.guild, category)

        if not category:
            await interaction.followup.send(
                "I could not create a ticket channel because all channel categories are full "
                "and I lack permissions to create a new one. Please contact a server administrator.",
                ephemeral=True
            )
            return None

        ticket_name = f"{ticket.category.value}-{await self.ticket_num(category=ticket.category.value)}"
        topic = await self.topic_metadata(ticket)
        channel_params = {
            "name": ticket_name,
            "category": target_category,
            "overwrites": ticket.get_overwrites(interaction),
            "topic": topic
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
                ephemeral=True
            )
        except discord.HTTPException as e:
            log.error(f"An unexpected HTTP error occurred while creating channel '{ticket_name}': {e}")
            await interaction.followup.send(
                "An unexpected error occurred while creating your ticket. Please try again later.",
                ephemeral=True
            )

    def get_category(self, channel: discord.TextChannel) -> TicketCategory:
        """
        Extracts the ticket category from the channel topic.
        Falls back to None if no valid category is found.
        """
        if not channel.topic:
            raise ValueError(f"Tickets: {channel.name} topic is empty.")
        topic_data = self.parse_ticket_topic(channel.topic)
        category_str = topic_data.get("ticket category", "").lower()
        try:
            return TicketCategory(category_str)
        except ValueError as e:
            raise ValueError(
                f"{channel.name}[ID:{channel.id}]: Unknown 'Ticket Category' in topic: {category_str}"
            ) from e

    async def load_tickets(self) -> None:
        guild = self.bot.get_guild(Guilds.DDNET)
        for category in guild.categories:
            if category.name == "Tickets":
                for channel in category.text_channels:
                    if channel.id in (Channels.TICKETS_TRANSCRIPTS, Channels.TICKETS_INFO):
                        continue
                    await self.create_ticket(channel=channel)

    async def create_ticket(
            self,
            channel: Optional[discord.TextChannel] = None,
            ticket: Optional[Ticket] = None,
            init: bool = False
    ) -> Ticket:
        """|coro|
        Create or register a ticket from a Discord text channel or from a new Ticket object.
        Uses the channel.topic to determine creator, category, and other metadata.
        """
        # Case: Ticket object already exists
        if ticket:
            self.add_ticket(channel=ticket.channel, ticket=ticket)
            if init:
                await self.bot.upsert(
                    queries.create_ticket,
                    ticket.creator.id,
                    ticket.channel.id,
                    ticket.category
                )
            return ticket

        if not channel or not channel.topic:
            raise ValueError("Channel or its topic is missing for ticket creation.")

        topic_metadata = self.parse_ticket_topic(channel.topic)

        try:
            creator_id = int(re.search(r"\d+", topic_metadata["Ticket Author"]).group())
        except (KeyError, AttributeError) as e:
            raise ValueError(
                f"{channel.name}[ID:{channel.id}]: Missing or invalid 'Ticket Author' in topic."
            ) from e
        creator = await self.bot.get_or_fetch_member(
            guild=self.bot.get_guild(Guilds.DDNET),
            user_id=creator_id,
        )

        category_str = topic_metadata.get("Ticket Category", "")
        try:
            category = TicketCategory(category_str)
        except ValueError as e:
            raise ValueError(
                f"{channel.name}[ID:{channel.id}]: Unknown 'Ticket Category' in topic: {category_str}"
            ) from e

        state = next((s for s in TicketState if s.value == channel.name[0]), TicketState.UNCLAIMED)

        result = await self.bot.fetch(queries.get_ticket_status, channel.id)
        if not result:
            locked = False
        elif isinstance(result, tuple):
            locked = bool(result[1]) if len(result) == 2 else bool(result[0])
        else:
            locked = bool(result)

        messages = [
            m async for m in channel.history(limit=10, oldest_first=True)
            if m.author and m.author.id == channel.guild.me.id
        ]
        if not messages:
            raise ValueError(f"No bot messages found in ticket channel: {channel.name}")

        start_message, info_message, close_message = messages[:3]

        profiles = []
        appeal_data = None

        try:
            if category == TicketCategory.RENAME:
                profiles = await self.extract_rename_data_from_topic(topic_metadata)
            elif category == TicketCategory.BAN_APPEAL:
                appeal_data = self.extract_appeal_data_from_topic(topic_metadata)
        except ValueError as e:
            log.warning(f"{channel.name}[ID:{channel.id}]: {e}")

        # Register the ticket
        async with self.lock:
            ticket = Ticket(
                channel=channel,
                creator=creator,
                category=category,
                start_message=start_message,
                info_message=info_message,
                close_message=close_message,
                state=state,
                rename_data=profiles,
                appeal_data=appeal_data,
                locked=locked,
            )
            self.add_ticket(channel=channel, ticket=ticket)
            return ticket

    async def change_category(self, ticket: Ticket, category: TicketCategory) -> None:
        """|coro|
        Change the category of an existing ticket.
        The change is also reflected in the database.

        Args:
            ticket (Ticket): The ticket object whose category is to be changed.
            category (Ticket.category): The new category to assign to the ticket.
        """

        ticket = await self.get_ticket(ticket.channel)
        ticket.category = category
        await self.bot.upsert(queries.change_category, category, ticket.channel.id, ticket.creator.id)

    async def update_ticket(
            self,
            interaction: discord.Interaction,
            *,
            ticket: Ticket,
            category: TicketCategory | None = None,
            rename_data: RenameData | None = None,
            appeal_data: AppealData | None = None,
            button: discord.ui.Button | None = None,
    ):
        # await interaction.response.defer(ephemeral=True)
        from .views.containers.close import CloseContainer
        category_changed = category is not None and ticket.category != category

        if rename_data is not None:
            ticket.rename_data = rename_data

        if appeal_data is not None:
            ticket.appeal_data = appeal_data

        if category_changed:
            ticket.category = category

        container_map = {
            TicketCategory.REPORT: lambda ticket: ReportContainer(ticket),
            TicketCategory.BAN_APPEAL: lambda ticket: BanAppealContainer(ticket),
            TicketCategory.COMPLAINT: lambda ticket: ComplaintContainer(ticket),
            TicketCategory.ADMIN_MAIL: lambda ticket: AdminMailContainer(ticket),
            TicketCategory.COMMUNITY_APP: lambda ticket: CommunityAppContainer(ticket),
            TicketCategory.RENAME: lambda _: RenameContainer(),
        }

        embed_map = {
            TicketCategory.REPORT: embeds.ReportInfoEmbed(interaction.guild),
            TicketCategory.RENAME: embeds.RenameInfoEmbed(ticket) if ticket.rename_data else None,
            TicketCategory.BAN_APPEAL: embeds.BanAppealInfoEmbed(ticket) if ticket.appeal_data else None,
            TicketCategory.COMPLAINT: embeds.ComplaintInfoEmbed(interaction.user),
            TicketCategory.ADMIN_MAIL: embeds.AdminMailInfoEmbed(),
            TicketCategory.COMMUNITY_APP: embeds.AdminMailInfoEmbed(),
        }

        await ticket.start_message.edit(view=container_map[ticket.category](ticket))
        await ticket.info_message.edit(embed=embed_map[ticket.category])
        await ticket.close_message.edit(view=CloseContainer.for_category(ticket.category))

        if button is not None:
            button.disabled = True
            await interaction.message.edit(view=button.view)

        overwrites = ticket.get_overwrites(interaction)

        topic = await self.topic_metadata(ticket)

        await ticket.channel.edit(
            name=f"{ticket.category.value}-{await self.ticket_num(category=ticket.category.value)}",
            topic=topic,
            overwrites=overwrites,
        )

        await interaction.channel.send(
            f"{ticket.creator.mention} ticket channel category changed to "
            f"**{ticket.category.name}**. Kindly review {ticket.start_message.jump_url}."
        )

        await interaction.delete_original_response()
        # await interaction.response.send_message("abc")
        await self.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)

    async def topic_metadata(self, ticket: Ticket):
        base_lines = [
            f"Ticket Author: <@{ticket.creator.id}>",
            f"Ticket Category: {ticket.category.value}",
        ]

        extra = []

        if ticket.category == TicketCategory.RENAME and ticket.rename_data:
            extra.extend([
                f"Old Name: {ticket.rename_data.old_profile.name}",
                f"New Name: {ticket.rename_data.new_profile.name}",
            ])

        if ticket.category == TicketCategory.BAN_APPEAL and ticket.appeal_data:
            extra.extend([
                f"Appeal Name: {ticket.appeal_data.name}",
                f"Appeal Address: {ticket.appeal_data.address}",
                f"Appeal DNSBL: {ticket.appeal_data.dnsbl}",
                f"Appeal Reason: {ticket.appeal_data.reason}",
                f"Appeal Statement: {ticket.appeal_data.appeal}",
            ])

        return "\n".join(base_lines + extra)

    def add_ticket(self, ticket: Ticket, channel: Optional[discord.TextChannel]):
        """
        Add (duh) a ticket to the internal management system.
        Args:
            channel (discord.TextChannel): The text channel to which the ticket is associated.
            ticket (Ticket): The ticket object to be added to the management system.
        """
        self.tickets[channel.id] = ticket

    async def del_ticket(
            self,
            channel: Optional[discord.TextChannel] = None,
            ticket: Optional[Ticket] = None
    ):
        """|coro|
        Deletes a ticket from the internal management system and Database.

        Args:
            channel (Optional[discord.TextChannel]): The text channel associated with the ticket to be deleted.
            ticket (Optional[Ticket]): The ticket object representing the ticket to be deleted.
        """
        if channel:
            ticket = await self.get_ticket(channel)

        # TODO: Get ticket from channel object
        async with self.lock:
            if ticket:
                await self.bot.upsert(queries.delete_ticket, ticket.channel.id, ticket.creator.id)
                del self.tickets[ticket.channel.id]

    async def get_ticket(self, channel: discord.TextChannel) -> Ticket:
        """|coro|
        Retrieve the ticket associated with a specific text channel.
        If the ticket is not found, it logs an error and attempts to create a ticket object for that channel.

        Args:
            channel (discord.TextChannel): The text channel for which to retrieve the ticket.

        Returns:
            Ticket: The ticket object associated with the specified channel, or a newly created ticket if none exists.
        """

        if channel.id not in self.tickets:
            log.error(
                f"Ticket object for channel ID {channel.id} not found. Was the ticket detached? "
                f"Can also happen due to DiscordServerError exceptions. \n"
                f"Attempting to generate ticket object..."
            )
            with (contextlib.suppress(discord.errors.NotFound)):
                channel = await self.bot.fetch_channel(channel.id)
                if channel:
                    ch = await self.create_ticket(channel=channel)
                    log.error("Success!")
                    return ch
        return self.tickets.get(channel.id)

    async def set_lock(self, ticket: Ticket, locked: bool):
        """
        Updates the ticket's locked state in the database and sets it on the object.

        Parameters:
            ticket (Ticket): The ticket to update.
            locked (bool): Whether the ticket should be marked as locked or not.
        """
        query = """
                UPDATE discordbot_tickets
                SET locked = %s
                WHERE channel_id = %s; \
                """
        await self.bot.upsert(query, locked, ticket.channel.id)
        ticket.locked = locked

    async def toggle_ticket_lock(
            self,
            ticket: Ticket,
            send_msg: bool = True,
            force_state: Optional[bool] = None
    ) -> Optional[discord.Message]:
        """Toggle or force the locked state of a ticket channel and update permissions.

        Args:
            ticket (Ticket): The ticket whose lock state should be toggled or set.
            send_msg: Whether the lock message should be sent or not.
            force_state: If True/False, forces the ticket to that lock state. If None, toggles.

        Returns:
            Optional[discord.Message]: The message sent to the channel indicating the new lock state.
        """
        lock_state = force_state if force_state is not None else not ticket.locked  # toggle if force not provided

        overwrite = ticket.channel.overwrites_for(ticket.creator)
        overwrite.send_messages = not lock_state

        await ticket.channel.set_permissions(ticket.creator, overwrite=overwrite)

        ticket.locked = lock_state
        await self.set_lock(ticket, lock_state)

        if send_msg:
            return await ticket.channel.send(
                content=f"The ticket has been {'locked' if ticket.locked else 'unlocked'}."
            )
        return None

    async def check_for_open_ticket(
            self,
            interaction: discord.Interaction | None,
            category: TicketCategory,
    ) -> discord.TextChannel | None:
        """
        Returns the open ticket channel for a user and category, or None if none exists.
        """
        channel = next(
            (
                ticket.channel
                for ticket in self.tickets.values()
                if ticket.creator == interaction.user and ticket.category == category
            ),
            None,
        )

        if channel and interaction:
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )

        return channel

    async def mentions(self, interaction: discord.Interaction, category):
        """|coro|
        Generate a mention string for users subscribed to a specific category.

        Args:
            interaction (discord.Interaction): The discord interaction object
            category: The category for which to retrieve subscriber user IDs.

        Returns:
            str: A string containing mentions of all subscribers and the interaction user.
        """

        fetch_query = """
                      SELECT user_id
                      FROM discordbot_subscriptions
                      WHERE category = %s;
                      """
        user_ids = await self.bot.fetch(fetch_query, category, fetchall=True)

        mention_subscribers = [f"<@{user_id[0]}>" for user_id in user_ids]
        return " ".join(mention_subscribers) + f" {interaction.user.mention}"

    async def ticket_num(self, category) -> int:
        """|coro|
        Retrieve and update the ticket count for a specific category.

        Args:
            category: The ticket category for which to retrieve and update the ticket count.
        Returns:
            int: The updated ticket count for the specified category.
        """

        async with self.lock:
            ticket_num = await self.bot.fetch(queries.get_ticket_num, category)
            ticket_num = int(ticket_num[0]) + 1 if ticket_num else 1
            await self.bot.upsert(queries.update_ticket_num, category, ticket_num, ticket_num)
            return ticket_num

    async def extract_rename_data_from_topic(self, topic_data: dict[str, str]) -> RenameData:
        old_name = topic_data.get("Old Name")
        new_name = topic_data.get("New Name")

        if not old_name or not new_name:
            raise ValueError("Missing rename metadata in channel topic.")

        return RenameData(
            old_profile=await PlayerProfile.from_database(self.bot, old_name),
            new_profile=await PlayerProfile.from_database(self.bot, new_name),
        )

    def extract_appeal_data_from_topic(self, topic_data: dict[str, str]) -> AppealData:
        required_keys = {
            "Appeal Name",
            "Appeal Address",
            "Appeal DNSBL",
            "Appeal Reason",
            "Appeal Statement",
        }

        if missing := required_keys - topic_data.keys():
            raise ValueError(f"Missing appeal metadata in channel topic: {missing}")

        return AppealData(
            name=topic_data["Appeal Name"],
            address=topic_data["Appeal Address"],
            dnsbl=topic_data["Appeal DNSBL"],
            reason=topic_data["Appeal Reason"],
            appeal=topic_data["Appeal Statement"],
        )
