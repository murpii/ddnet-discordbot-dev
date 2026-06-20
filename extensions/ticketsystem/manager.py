import asyncio
import contextlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
import discord

import extensions.ticketsystem.queries as queries
from constants import Guilds, Channels, Emojis
from utils.profile import PlayerProfile
from .mappings import START_CONTAINERS
from .ticket import Ticket, AppealData, TicketCategory, TicketState, RenameData
from .transcript import TicketTranscript
from .views.containers.close import CloseContainer

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
        """Parse a ticket topic into a dictionary of fields"""
        data = {}
        for line in topic.splitlines():
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
        return data

    @staticmethod
    def is_ticket_category(category: Optional[discord.CategoryChannel]) -> bool:
        """Whether a Discord category holds ticket channels"""
        if category is None:
            return False
        if category.name.startswith("Tickets") or category.name == "Community Applications":
            return True
        return bool(Channels.CAT_COMMUNITY_APPS) and category.id == Channels.CAT_COMMUNITY_APPS

    async def get_community_app_category(
            self, guild: discord.Guild
    ) -> Optional[discord.CategoryChannel]:
        """Resolve the Community Applications category: configured id, else by name, else create it"""
        if Channels.CAT_COMMUNITY_APPS:
            category = guild.get_channel(Channels.CAT_COMMUNITY_APPS)
            if isinstance(category, discord.CategoryChannel):
                return category

        category = discord.utils.get(guild.categories, name="Community Applications")
        if category is not None:
            return category

        tickets_cat = guild.get_channel(Channels.CAT_TICKETS)
        overwrites = tickets_cat.overwrites if isinstance(tickets_cat, discord.CategoryChannel) else None
        try:
            new_category = await guild.create_category(name="Community Applications", overwrites=overwrites)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.error("Failed to create '%s' category: %s", "Community Applications", e)
            return None

        # place it right below the main ticket category
        if isinstance(tickets_cat, discord.CategoryChannel):
            with contextlib.suppress(discord.HTTPException):
                await new_category.move(after=tickets_cat, reason="Keep community apps below tickets")

        return new_category

    async def load_tickets(self) -> None:
        guild = self.bot.get_guild(Guilds.DDNET)
        channels = [
            channel
            for category in guild.categories if self.is_ticket_category(category)
            for channel in category.text_channels
            if channel.id not in (Channels.TICKETS_TRANSCRIPTS, Channels.TICKETS_INFO)
        ]

        for i in range(0, len(channels), 10):
            batch = channels[i:i + 10]
            results = await asyncio.gather(
                *(self.create_ticket(channel=ch) for ch in batch),
                return_exceptions=True,
            )
            for ch, result in zip(batch, results):
                if isinstance(result, Exception):
                    log.error("Failed to load ticket %s: %s", ch.name, result)

    async def cleanup_database(self) -> str:
        """Removes ticket rows whose channels no longer exist"""
        rows = await self.bot.fetch("SELECT channel_id FROM discordbot_tickets", fetchall=True)
        orphans = [row[0] for row in rows if int(row[0]) not in self.tickets]

        if not orphans:
            return "No orphaned tickets found, nothing was deleted."

        placeholders = ", ".join(["%s"] * len(orphans))
        await self.bot.upsert(
            f"DELETE FROM discordbot_tickets WHERE channel_id IN ({placeholders})", *orphans
        )
        return "Deleted tickets:\n" + "\n".join(f"Channel ID: {cid}" for cid in orphans)

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
        # Case: A ticket object already exists
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
        locked = bool(result[0]) if result else False

        messages = [
            m async for m in channel.history(limit=10, oldest_first=True)
            if m.author and m.author.id == channel.guild.me.id
        ]
        if not messages:
            raise ValueError(f"No bot messages found in ticket channel: {channel.name}")

        start_message, close_message = messages[:2]

        profiles = []
        appeal_data = None

        try:
            if category == TicketCategory.RENAME:
                profiles = await self.extract_rename_data_from_topic(topic_metadata)
            elif category in (TicketCategory.BAN_APPEAL, TicketCategory.VPN_BAN_APPEAL):
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
        # the modal flows defer before calling this whereas the `/change_category` command
        # path does not, so ensure there's an original response to clean up at the end
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        category_changed = category is not None and ticket.category != category

        if rename_data is not None:
            ticket.rename_data = rename_data

        if appeal_data is not None:
            ticket.appeal_data = appeal_data

        if category_changed:
            ticket.category = category

        await ticket.start_message.edit(view=START_CONTAINERS[ticket.category](ticket))
        await ticket.close_message.edit(view=CloseContainer.for_category(ticket.category))

        if button is not None:
            button.disabled = True
            await interaction.message.edit(view=button.view)

        overwrites = ticket.get_overwrites(interaction)
        topic = self.topic_metadata(ticket)

        await ticket.channel.edit(
            name=f"{ticket.category.value}-{await self.ticket_num(category=ticket.category.value)}",
            topic=topic,
            overwrites=overwrites,
        )

        await interaction.channel.send(
            f"{ticket.creator.mention} ticket channel category changed to "
            f"**{ticket.category.name}**. Kindly review {ticket.start_message.jump_url}."
        )

        with contextlib.suppress(discord.NotFound):
            await interaction.delete_original_response()
        await self.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)

    def topic_metadata(self, ticket: Ticket) -> str:
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

        if ticket.category in (TicketCategory.BAN_APPEAL, TicketCategory.VPN_BAN_APPEAL) and ticket.appeal_data:
            extra.extend([
                f"Appeal Name: {ticket.appeal_data.name}",
                f"Appeal Address: {ticket.appeal_data.address}",
                f"Appeal DNSBL: {ticket.appeal_data.dnsbl}",
            ])
            # VPN appeals have no ban reason or appeal statement, so don't store empty keys
            if ticket.category == TicketCategory.BAN_APPEAL:
                extra.extend([
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

    async def close_ticket(
            self,
            interaction: Optional[discord.Interaction],
            ticket: Ticket,
            *,
            message: Optional[str] = None,
            closer: Optional[discord.abc.User] = None,
    ) -> None:
        """Run the full close lifecycle, shared by /close and the confirm buttons:
        post the closing message, build + DM the transcript, drop the ticket, then
        delete the channel (and its category if it is now empty).
        """
        closer = closer or (interaction.user if interaction else None)
        async with ticket.lock:
            ticket.being_closed = True
            try:
                if interaction and not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True, thinking=True)
                if message:
                    await ticket.channel.send(message)

                await TicketTranscript(self.bot, ticket).run(interaction, message, closer=closer)
                await self.del_ticket(ticket=ticket)

                closer_info = f"{closer} [ID: {closer.id}]" if closer else "an automated close"
                log.info(
                    f"{closer_info} closed a "
                    f"{ticket.category.value.title()} ticket made by {ticket.creator} "
                    f"[ID: {ticket.creator.id}]. Removed channel {ticket.channel.name} "
                    f"[ID: {ticket.channel.id}]"
                )

                if interaction:
                    with contextlib.suppress(discord.NotFound):
                        await interaction.edit_original_response(content="Closing Ticket...")

                category = ticket.channel.category
                await ticket.channel.delete()
                if category and len(category.channels) == 0:
                    await category.delete()
            except Exception as e:
                log.exception(f"{ticket.channel.name}: Error during ticket closure:\n{e}")
                if interaction is None:
                    raise  # let the bulk caller count this ticket as a failure
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"An error occurred while closing the ticket:\n{e}", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"An error occurred while closing the ticket:\n{e}", ephemeral=True
                    )
            finally:
                ticket.being_closed = False

    def neglect_message(self) -> str:
        tear = self.bot.get_emoji(Emojis.TEAR)
        return f"Sorry, looks like no one was around at the time to check. {tear}"

    def neglected_report_tickets(self, hours: int) -> list[Ticket]:
        """
        Unresponded Report tickets whose channel is older than x hours.
        Only UNCLAIMED tickets count as neglected
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [
            ticket for ticket in self.tickets.values()
            if ticket.category == TicketCategory.REPORT
               and ticket.state == TicketState.UNCLAIMED
               and not ticket.being_closed
               and ticket.channel.created_at <= cutoff
        ]

    async def bulk_close_neglected(
            self,
            tickets: list[Ticket],
            closer: Optional[discord.abc.User],
    ) -> tuple[int, int]:
        message = self.neglect_message()
        closed = failed = 0
        for ticket in tickets:
            try:
                await self.close_ticket(None, ticket, message=message, closer=closer)
                closed += 1
            except Exception:
                log.exception("Bulk close failed for %s", ticket.channel.name)
                failed += 1
        return closed, failed

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
        }

        if missing := required_keys - topic_data.keys():
            raise ValueError(f"Missing appeal metadata in channel topic: {missing}")

        return AppealData(
            name=topic_data["Appeal Name"],
            address=topic_data["Appeal Address"],
            dnsbl=topic_data["Appeal DNSBL"],
            reason=topic_data.get("Appeal Reason", ""),
            appeal=topic_data.get("Appeal Statement", ""),
        )
