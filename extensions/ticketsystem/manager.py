import asyncio
import contextlib
import logging
import re
import json
from dataclasses import dataclass, field
from typing import Optional, Union
from enum import Enum
import discord
from discord import PermissionOverwrite

import extensions.ticketsystem.queries as queries
from constants import Guilds, Channels, Roles
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")

class TicketCategory(Enum):
    REPORT = "report"
    RENAME = "rename"
    BAN_APPEAL = "ban-appeal"
    COMPLAINT = "complaint"
    ADMIN_MAIL = "admin-mail"


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
class Ticket:
    channel: discord.TextChannel | None
    creator: discord.User
    category: TicketCategory
    state: TicketState = TicketState.UNCLAIMED
    rename_data: list[PlayerProfile] = field(default_factory=list, init=True) # TODO use RenameData dataclass
    appeal_data: AppealData = None
    inactivity: int # Set to 0 initially by the create_ticket method
    being_closed: bool = False
    locked: bool = False
    lock: asyncio.Lock = field(init=False, repr=False)
    overwrites: dict[discord.Role | discord.Member, PermissionOverwrite] = field(init=False, repr=False)

    def __post_init__(self):
        self.lock = asyncio.Lock()

    def __repr__(self) -> str:
        player_repr = [str(p) for p in self.rename_data] if self.rename_data else []
        appeal_data = [str(p) for p in self.appeal_data] if self.appeal_data else []
        return json.dumps(
            {
                "name": str(self.channel),
                "channel-id": str(self.channel.id) if self.channel else None,
                "creator": str(self.creator),
                "category": str(self.category),
                "state": str(self.state),
                "rename_data": player_repr,
                "appeal_data": appeal_data,
                "inactivity_count": self.inactivity,
                "locked": self.locked,
                "being_closed": self.being_closed,
            },
            indent=4
        )

    def get_overwrites(
            self,
            interaction: discord.Interaction
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """Returns the overwrites based on the ticket category"""
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                      interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                      self.creator: discord.PermissionOverwrite(read_messages=True, send_messages=True)}

        if self.category in [TicketCategory.REPORT, TicketCategory.BAN_APPEAL]:
            overwrites[interaction.guild.get_role(Roles.DISCORD_MODERATOR)] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True)
            overwrites[interaction.guild.get_role(Roles.MODERATOR)] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True)

        elif self.category in [TicketCategory.RENAME, TicketCategory.ADMIN_MAIL, TicketCategory.COMPLAINT]:
            overwrites[interaction.guild.get_role(Roles.DISCORD_MODERATOR)] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True)

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
            new_name = f"{prefix}{self.channel.name}"
            await self.channel.edit(name=new_name)


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

    category_mapping = {
        "report": TicketCategory.REPORT,
        "rename": TicketCategory.RENAME,
        "ban-appeal": TicketCategory.BAN_APPEAL,
        "complaint": TicketCategory.COMPLAINT,
        "admin-mail": TicketCategory.ADMIN_MAIL,
    }

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

        if ticket:
            self.add_ticket(channel=ticket.channel, ticket=ticket)
            if init:
                await self.bot.upsert(queries.create_ticket, ticket.creator.id, ticket.channel.id, ticket.category)
            return ticket

        if not channel or not channel.topic:
            raise ValueError("Channel or its topic is missing for ticket creation.")

        match = re.search(r"<@!?(\d+)>", channel.topic)
        if not match:
            raise ValueError(f"{channel.name}[ID:{channel.id}]: "
                             f"Malformed channel topic, unable to extract ticket creator.")

        creator_id = int(match[1])
        guild = self.bot.get_guild(Guilds.DDNET)
        creator = await self.bot.get_or_fetch_member(guild=guild, user_id=creator_id)

        state = next((s for s in TicketState if s.value == channel.name[0]), TicketState.UNCLAIMED)
        category = self.get_category(channel)

        result = await self.bot.fetch(queries.get_ticket_status, channel.id)
        inactivity = result[0] if result else 0
        locked = result[1] if result else False

        profiles, appeal_data = [], []
        if category in (TicketCategory.RENAME, TicketCategory.BAN_APPEAL):
            messages = [m async for m in channel.history(limit=2, oldest_first=True)]
            if len(messages) < 2 or not messages[1].embeds:
                log.warning(
                    f"Channel {channel.name} is missing expected embed data. Continuing without extracted data. "
                    f"This usually happens if the ticket category was changed manually.")
            else:
                embed = messages[1].embeds[0]
                if category == TicketCategory.RENAME:
                    profiles = await self.extract_data_from_embed(embed, rename=True)
                elif category == TicketCategory.BAN_APPEAL:
                    appeal_data = await self.extract_data_from_embed(embed, appeal=True)

        async with self.lock:
            ticket = Ticket(
                channel=channel,
                creator=creator,
                category=category,
                state=state,
                rename_data=profiles,
                appeal_data=appeal_data,
                inactivity=inactivity,
                locked=locked,
            )
            self.add_ticket(channel=channel, ticket=ticket)
            return ticket

    async def change_ticket(self, ticket: Ticket, category: str) -> None:
        """|coro|
        Change the category of an existing ticket.
        The change is also reflected in the database.

        Args:
            ticket (Ticket): The ticket object whose category is to be changed.
            category (Ticket.category): The new category to assign to the ticket.
        """

        ticket = await self.get_ticket(ticket.channel)
        category = self.category_mapping.get(category.lower())
        ticket.category = category
        await self.bot.upsert(queries.change_category, category, ticket.channel.id, ticket.creator.id)
        ticket.category = category

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
        If the ticket is not found, it logs an error and creates a new ticket for that channel.

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
        UPDATE discordbot_tickets SET locked = %s WHERE channel_id = %s;
        """
        await self.bot.upsert(query, locked, ticket.channel.id)
        ticket.locked = locked

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
        SELECT user_id FROM discordbot_subscriptions WHERE category = %s;
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

    async def extract_data_from_embed(
            self,
            embed: discord.Embed,
            *,
            rename: bool = False,
            appeal: bool = False
    ) -> list[PlayerProfile] | AppealData | None:
        if rename:
            old_name = None
            new_name = None
            for field in embed.fields:  # noqa
                if "Current Name" in field.value:
                    old_name = field.value.split("```")[1]
                elif "New Name" in field.value:
                    new_name = field.value.split("```")[1]

            if old_name is None or new_name is None:
                raise ValueError("Could not extract old or new name from the embed.")

            profile_old, profile_new = await asyncio.gather(
                PlayerProfile.from_database(self.bot, old_name),
                PlayerProfile.from_database(self.bot, new_name),
            )
            return [profile_old, profile_new]
        elif appeal:
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
            else:
                raise ValueError("Could not extract appeal data from the embed.")
        return None
