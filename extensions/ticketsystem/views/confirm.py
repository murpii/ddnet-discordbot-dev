import logging
from typing import Optional

import discord
from discord.ui import Button

from extensions.ticketsystem.manager import Ticket
from extensions.ticketsystem.transcript import TicketTranscript
from constants import Roles, Emojis
from utils.checks import is_staff, check_dm_channel

log = logging.getLogger("tickets")


class BaseConfirmView(discord.ui.View):
    def __init__(self, bot, closing: bool = True, message: Optional[str] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.closing = closing
        self.message = message

    async def transcript(self, interaction: discord.Interaction, ticket, message: Optional[str] = None):
        """|coro|
        Generates and sends a transcript of the ticket.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
            ticket: The ticket for which the transcript is being created.
            message (Optional[str]): The message sent to the ticket creator, if any.
        """
        transcript = TicketTranscript(self.bot, ticket)
        await transcript.create_transcript(interaction)
        await transcript.notify_ticket_creator(interaction, postscript=message)
        transcript.cleanup()

    async def handle_ticket_closure(
            self,
            interaction: discord.Interaction,
            ticket: Ticket,
            message: Optional[str] = None
    ):
        if message:
            self.message = message
        async with ticket.lock:
            ticket.being_closed = True
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
                if self.message:
                    await ticket.channel.send(self.message)
                await self.transcript(interaction, ticket, message)
                await self.ticket_manager.del_ticket(ticket=ticket)

                log.info(
                    f"{interaction.user} [ID: {interaction.user.id}] "
                    f"closed a {ticket.category.value.title()} ticket made by {ticket.creator} [ID: {ticket.creator.id}]. "
                    f"Removed channel named {interaction.channel.name} [ID: {interaction.channel_id}]"
                )

                if interaction.response.is_done():
                    await interaction.edit_original_response(content="Closing Ticket...")
                    await interaction.channel.delete()
                    if len(interaction.channel.category.channels) == 0:
                        await interaction.channel.category.delete()
            except Exception as e:
                log.exception(f"{ticket.channel.name}: Error during ticket closure: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while closing the ticket.",
                                                            ephemeral=True)
                else:
                    await interaction.followup.send("An error occurred while closing the ticket.", ephemeral=True)
            finally:
                ticket.being_closed = False


class ConfirmView(BaseConfirmView):
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm:close_ticket")
    async def confirm(self, interaction: discord.Interaction, _: Button):
        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        if (
                interaction.user != ticket.creator
                and not is_staff(
            interaction.user,
            roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
        )
        ):
            await interaction.response.send_message(content="This ticket does not belong to you.", ephemeral=True)
            return

        if ticket.being_closed:
            await interaction.response.send_message(content="Ticket is already being closed.", ephemeral=True)
            return

        if ticket is None:
            return

        if self.closing:
            await self.handle_ticket_closure(interaction, ticket)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancel:close_ticket")
    async def cancel(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer()  # noqa
        await interaction.delete_original_response()


class ConfirmViewStaff(BaseConfirmView):
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm:close_ticket_staff")
    async def confirm(self, interaction: discord.Interaction, _: Button):
        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        if (
                interaction.user != ticket.creator
                and not is_staff(
            interaction.user,
            roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
        )
        ):
            await interaction.response.send_message(content="This ticket does not belong to you.", ephemeral=True)
            return

        if ticket.being_closed:
            await interaction.response.send_message(content="Ticket is already being closed.", ephemeral=True)
            return

        if ticket is None:
            return

        await self.handle_ticket_closure(interaction, ticket)

    @discord.ui.button(label="Confirm, due to Inactivity.", style=discord.ButtonStyle.green,
                       custom_id="confirm:close_inactivity")
    async def close_inactivity(self, interaction: discord.Interaction, _: Button):
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        if (
                interaction.user != ticket.creator
                and not is_staff(
            interaction.user,
            roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
        )
        ):
            await interaction.response.send_message(content="This ticket does not belong to you.", ephemeral=True)
            return

        if ticket.being_closed:
            await interaction.response.send_message(content="Ticket is already being closed.", ephemeral=True)
            return

        if ticket is None:
            return

        message = "Your ticket has been closed due to inactivity."
        await self.handle_ticket_closure(interaction, ticket, message)

    @discord.ui.button(label="Confirm, due to neglect.", style=discord.ButtonStyle.green,
                       custom_id="confirm:close_neglected")
    async def close_neglect(self, interaction: discord.Interaction, _: Button):
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        if (
                interaction.user != ticket.creator
                and not is_staff(
            interaction.user,
            roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
        )
        ):
            await interaction.response.send_message(content="This ticket does not belong to you.", ephemeral=True)
            return

        if ticket.being_closed:
            await interaction.response.send_message(content="Ticket is already being closed.", ephemeral=True)
            return

        if ticket is None:
            return

        tear = self.bot.get_emoji(Emojis.TEAR)
        message = f"Sorry, looks like no one was around at the time to check. {tear}"
        await self.handle_ticket_closure(interaction, ticket, message)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancel:close_ticket")
    async def cancel(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer()  # noqa
        await interaction.delete_original_response()
