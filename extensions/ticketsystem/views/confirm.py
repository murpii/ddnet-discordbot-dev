from typing import Optional

import discord

from constants import Roles, Emojis
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.checks import is_staff

STAFF_ROLES = [Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]


class BaseConfirmView(discord.ui.LayoutView):
    """Confirmation prompt shown before a ticket is closed"""

    DEFAULT_PROMPT = "Are you sure you want to close the ticket?"

    def __init__(
            self,
            bot,
            closing: bool = True,
            message: Optional[str] = None,
            prompt: Optional[str] = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.closing = closing
        self.message = message
        self.prompt = prompt or self.DEFAULT_PROMPT

    def build(self, buttons: list[discord.ui.Button]) -> None:
        """Assembles the container prompt text + the confirm/cancel buttons"""
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(self.prompt),
                large_seperator(),
                discord.ui.ActionRow(*buttons),
                accent_colour=TICKET_ACCENT,
            )
        )

    async def close_guard(self, interaction: discord.Interaction) -> Optional[Ticket]:
        """A shared guard. Returns the ticket if the user may close it, else None."""
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        if ticket is None:
            return None
        if interaction.user != ticket.creator and not is_staff(interaction.user, roles=STAFF_ROLES):
            await interaction.response.send_message(content="This ticket does not belong to you.", ephemeral=True)
            return None
        if ticket.being_closed:
            await interaction.response.send_message(content="Ticket is already being closed.", ephemeral=True)
            return None
        return ticket

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()  # noqa
        await interaction.delete_original_response()


class ConfirmView(BaseConfirmView):
    def __init__(self, bot, closing: bool = True, message: Optional[str] = None, prompt: Optional[str] = None):
        super().__init__(bot, closing, message, prompt)

        confirm_btn = discord.ui.Button(
            label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm:close_ticket"  # noqa
        )
        cancel_btn = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.red, custom_id="cancel:close_ticket"  # noqa
        )
        confirm_btn.callback = self.confirm
        cancel_btn.callback = self.cancel
        self.build([confirm_btn, cancel_btn])

    async def confirm(self, interaction: discord.Interaction):
        ticket = await self.close_guard(interaction)
        if ticket is None:
            return
        if self.closing:
            await self.ticket_manager.close_ticket(interaction, ticket, message=self.message)


class ConfirmViewStaff(BaseConfirmView):
    DEFAULT_PROMPT = (
        "Are you sure you want to close the ticket?\n"
        "Closing due to **neglect** will send an apology to the creator.\n"
        "Closing for **inactivity** alerts them of that reason."
    )

    def __init__(self, bot, closing: bool = True, message: Optional[str] = None, prompt: Optional[str] = None):
        super().__init__(bot, closing, message, prompt)

        confirm_btn = discord.ui.Button(
            label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm:close_ticket_staff"  # noqa
        )
        inactivity_btn = discord.ui.Button(
            label="Confirm, due to Inactivity.", style=discord.ButtonStyle.green,  # noqa
            custom_id="confirm:close_inactivity",
        )
        neglect_btn = discord.ui.Button(
            label="Confirm, due to neglect.", style=discord.ButtonStyle.green,  # noqa
            custom_id="confirm:close_neglected",
        )
        cancel_btn = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.red, custom_id="cancel:close_ticket"  # noqa
        )
        confirm_btn.callback = self.confirm
        inactivity_btn.callback = self.close_inactivity
        neglect_btn.callback = self.close_neglect
        cancel_btn.callback = self.cancel
        self.build([confirm_btn, inactivity_btn, neglect_btn, cancel_btn])

    async def confirm(self, interaction: discord.Interaction):
        ticket = await self.close_guard(interaction)
        if ticket is None:
            return
        await self.ticket_manager.close_ticket(interaction, ticket, message=self.message)

    async def close_inactivity(self, interaction: discord.Interaction):
        ticket = await self.close_guard(interaction)
        if ticket is None:
            return
        await self.ticket_manager.close_ticket(
            interaction, ticket, message="Your ticket has been closed due to inactivity."
        )

    async def close_neglect(self, interaction: discord.Interaction):
        ticket = await self.close_guard(interaction)
        if ticket is None:
            return
        tear = self.bot.get_emoji(Emojis.TEAR)
        await self.ticket_manager.close_ticket(
            interaction, ticket, message=f"Sorry, looks like no one was around at the time to check. {tear}"
        )
