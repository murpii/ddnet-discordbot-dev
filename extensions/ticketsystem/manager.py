import asyncio
import contextlib
import logging
import re
import json
from dataclasses import dataclass, field
from typing import Optional, Tuple, Union
from enum import Enum
import discord
from discord import PermissionOverwrite
from discord.ext import commands

import extensions.ticketsystem.queries as queries
from constants import Guilds, Channels
from utils.profile import PlayerProfile
from .utils import find_or_create_category

log = logging.getLogger("tickets")


class TicketCategory(Enum):
    REPORT = "report"
    RENAME = "rename"
    BAN_APPEAL = "ban-appeal"
    COMPLAINT = "complaint"
    ADMIN_MAIL = "admin-mail"
    COMMUNITY_APP = "community-app"


class TicketState(Enum):
    UNCLAIMED = ""
    CLAIMED = "✅"
    WAITING_FOR_RESPONSE = "☑"


@dataclass(slots=True, kw_only=True)
class AppealData:
    name: str
    address: str
    dnsbl: str
    reason: str
    appeal: str

    def __repr__(self) -> str:
        return json.dumps(
            {
                "name": str(self.name),
                "address": str(self.address),
                "dnsbl": str(self.dnsbl),
                "reason": str(self.reason),
                "appeal": str(self.appeal),
            },
            indent=4
        )


@dataclass(slots=True, kw_only=True)
class RenameData:
    old_profile: PlayerProfile
    new_profile: PlayerProfile

    def __repr__(self) -> str:
        return json.dumps(
            {
                "old_profile": self.old_profile,
                "new_profile": self.new_profile,
            },
            indent=4
        )


@dataclass(slots=True, kw_only=True)
class Ticket:
    channel: Optional[discord.TextChannel] = None
    creator: Union[discord.Member, discord.User] = None
    category: TicketCategory
    state: TicketState = TicketState.UNCLAIMED
    start_message: Optional[discord.Message] = None  # Ticket initial message
    info_message: Optional[discord.Message] = None  # Ticket info message
    close_message: Optional[discord.Message] = None  # Ticket closing message
    rename_data: list[PlayerProfile] = field(default_factory=list, init=True)  # TODO use RenameData dataclass
    appeal_data: AppealData | None = None
    being_closed: bool = False
    locked: bool = False
    lock: asyncio.Lock = field(init=False, repr=False)
    overwrites: dict[discord.Role | discord.Member, PermissionOverwrite] = field(init=False, repr=False)

    def __post_init__(self):
        self.lock = asyncio.Lock()

    def __repr__(self) -> str:
        player_repr = [str(p) for p in self.rename_data] if self.rename_data else []
        # appeal_data = [str(p) for p in self.appeal_data] if self.appeal_data else []
        return json.dumps(
            {
                "name": str(self.channel),
                "channel": self.channel or None,
                "creator": str(self.creator),
                "start_message": str(self.start_message),
                "info_message": str(self.info_message),
                "close_message": str(self.close_message),
                "category": str(self.category),
                "state": str(self.state),
                "rename_data": player_repr,
                "appeal_data": self.appeal_data,
                "locked": self.locked,
                "being_closed": self.being_closed,
            },
            indent=4,
            default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
        )

    def get_overwrites(
            self,
            interaction: discord.Interaction
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """Returns the overwrites based on the ticket category"""
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            self.creator: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        config = interaction.client.config
        roles_key = f"{self.category.value}"

        if config.has_option("TICKETS", roles_key):
            role_ids = [
                int(r.strip())
                for r in config.get("TICKETS", roles_key).split(",")
                if r.strip().isdigit()
            ]
            for role_id in role_ids:
                if role_obj := interaction.guild.get_role(role_id):
                    overwrites[role_obj] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        return overwrites

    async def set_state(self, state: TicketState) -> None:
        """|coro|
        Update the state of the ticket channel by modifying its name with a symbol.

        Args:
            state (TicketState): The new state to assign to the ticket channel.
        """
        self.state = state
        prefix = state.value
        if not self.channel.name.startswith(prefix):
            await self.channel.edit(name=f"{prefix}{self.channel.name}")


class TicketManager:
    """Manage the lifecycle of tickets within our Discord server.

    Attributes:
        tickets (dict): A dictionary mapping channel IDs to their corresponding ticket objects.
        lock (asyncio.Lock): A lock to manage concurrent access to ticket operations.
        category_mapping (dict): A mapping of category strings to their corresponding TicketCategory enums.
    """

    def __init__(self, bot):
        self.bot = bot
        self.tickets = {}
        self.lock = asyncio.Lock()
        self.cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, lambda i: i.user.id)

    # TODO: Remove this...
    category_mapping = {
        "report": TicketCategory.REPORT,
        "rename": TicketCategory.RENAME,
        "ban-appeal": TicketCategory.BAN_APPEAL,
        "complaint": TicketCategory.COMPLAINT,
        "admin-mail": TicketCategory.ADMIN_MAIL,
        "community-app": TicketCategory.COMMUNITY_APP,
    }

    async def create_channel(self, interaction: discord.Interaction, ticket: Ticket):
        """
        Creates a new ticket channel in an appropriate category.

        This function will handle full categories by creating a new category if necessary.
        """
        category = interaction.guild.get_channel(Channels.CAT_TICKETS)
        target_category = await find_or_create_category(interaction.guild, category)

        if not category:
            await interaction.followup.send(
                "I could not create a ticket channel because all ticket categories are full "
                "and I lack permissions to create a new one. Please contact a server administrator.",
                ephemeral=True
            )
            return None

        ticket_name = f"{ticket.category.value}-{await self.ticket_num(category=ticket.category.value)}"
        channel_params = {
            "name": ticket_name,
            "category": target_category,
            "overwrites": ticket.get_overwrites(interaction),
            "topic": f"Ticket author: <@{interaction.user.id}> | Category: {ticket.category.value}"
        }

        try:
            channel = await interaction.guild.create_text_channel(**channel_params)
            log.info(f"Successfully created ticket channel #{channel.name} ({channel.id})")
            return channel
        except discord.Forbidden:
            log.error(
                f"Failed to create ticket channel '{ticket_name}' in guild {interaction.guild.id}. Bot lacks 'Manage Channels' permission.")
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
        Extracts the category from the channel's name, handling possible state prefixes (like emojis).
        """
        name = next(
            (
                channel.name.removeprefix(state.value)
                for state in TicketState
                if state.value and channel.name.startswith(state.value)
            ),
            channel.name,
        )
        category_str = name.rsplit("-", 1)[0].strip().lower()
        return self.category_mapping.get(category_str)

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

        Args:
            channel (discord.TextChannel): The channel the ticket is based on.
            ticket (Ticket): An existing Ticket object to register.
            init (bool): Whether this is a freshly created ticket (triggered by button).

        Returns:
            Ticket: The ticket object tied to the specified channel.
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

        # Extract ticket creator ID from channel topic
        match = re.search(r"<@!?(\d+)>", channel.topic)
        if not match:
            raise ValueError(
                f"{channel.name}[ID:{channel.id}]: Malformed channel topic, unable to extract ticket creator."
            )

        creator_id = int(match[1])
        guild = self.bot.get_guild(Guilds.DDNET)
        creator = await self.bot.get_or_fetch_member(guild=guild, user_id=creator_id)

        # State
        state = next((s for s in TicketState if s.value == channel.name[0]), TicketState.UNCLAIMED)
        category = self.get_category(channel)

        # Lock Status
        result = await self.bot.fetch(queries.get_ticket_status, channel.id)
        locked = (result or (0, False))

        # Fetch initial messages
        messages = [
            m async for m in channel.history(limit=3, oldest_first=True)
            if m.author and m.author.id == channel.guild.me.id
        ]
        if not messages:
            raise ValueError(f"No messages found in ticket channel: {channel.name}")

        start_message = messages[0]
        if len(messages) > 2:
            info_message = messages[1]
            close_message = messages[2]
        else:
            info_message = None
            close_message = messages[1]

        profiles, appeal_data = [], None

        # Extract embed data for rename and ban appeal tickets
        if category in (TicketCategory.RENAME, TicketCategory.BAN_APPEAL):
            if len(messages) < 2 or not messages[1].embeds:
                log.warning(
                    f"Expected embed data not found in channel {channel.name}. "
                    f"Rename/Ban Appeal information will be skipped and omitted from the transcript. "
                    f"This often results from manual changes to the ticket category."
                )
            else:
                embed = messages[1].embeds[0]
                try:
                    if category == TicketCategory.RENAME:
                        profiles = await self.extract_rename_data(embed)
                    else:  # BAN_APPEAL
                        appeal_data = await self.extract_appeal_data(embed)
                except ValueError as e:
                    log.warning(
                        f"Invalid embed data in channel {channel.name} for {category.name}: {e}"
                    )

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

    async def change_ticket(self, ticket: Ticket, category: TicketCategory) -> None:
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

        overwrite = ticket.channel.overwrites_for(ticket.creator)  # type: ignore
        overwrite.send_messages = not lock_state

        await ticket.channel.set_permissions(ticket.creator, overwrite=overwrite)  # type: ignore

        ticket.locked = lock_state
        await self.set_lock(ticket, lock_state)

        if send_msg:
            return await ticket.channel.send(
                content=f"The ticket has been {'locked' if ticket.locked else 'unlocked'}."
            )
        return None

    def check_for_open_ticket(self, user: discord.User, category: Ticket.category) -> discord.TextChannel | None:
        """Returns ticket channels from a specific user and category."""
        return next(
            (
                ticket.channel
                for ticket in self.tickets.values()
                if ticket.creator == user and ticket.category == category
            ),
            None,
        )

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

    async def extract_rename_data(self, embed: discord.Embed) -> tuple[PlayerProfile, PlayerProfile]:
        old_name = None
        new_name = None
        for field in embed.fields:
            if "Current Name" in field.value:
                old_name = field.value.split("```")[1]
            elif "New Name" in field.value:
                new_name = field.value.split("```")[1]

        if old_name is None or new_name is None:
            raise ValueError("Could not extract old or new name from the embed.")

        return await asyncio.gather(
            PlayerProfile.from_database(self.bot, old_name),
            PlayerProfile.from_database(self.bot, new_name),
        )

    async def extract_appeal_data(self, embed: discord.Embed) -> AppealData:
        data = {}
        for f in embed.fields:
            name = f.name.lower()
            value = f.value.strip()

            if "ipv4" in name:
                parts = value.split("```")
                ip = parts[1] if len(parts) > 1 else None
                dnsbl = parts[-1].split("**")[1] if "**" in parts[-1] else None
                data["address"] = ip
                data["dnsbl"] = dnsbl

            elif "in-game name" in name:
                parts = value.split("```")
                data["name"] = parts[1] if len(parts) > 1 else None

            elif "ban reason" in name:
                data["reason"] = value

            elif "appeal statement" in name:
                data["appeal"] = value

        if all(key in data for key in ("address", "dnsbl", "name", "reason", "appeal")):
            return AppealData(
                name=data["name"],
                address=data["address"],
                dnsbl=data["dnsbl"],
                reason=data["reason"],
                appeal=data["appeal"],
            )

        raise ValueError("Could not extract appeal data from the embed.")
