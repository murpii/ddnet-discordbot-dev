import discord
import datetime
from datetime import datetime
import logging

from extensions.ticketsystem import embeds
from extensions.ticketsystem.queries import check_common_teamranks
from extensions.ticketsystem.ticket import Ticket, TicketCategory, RenameData
from extensions.ticketsystem.views.containers.close import CloseContainer
from extensions.ticketsystem.views.containers.rename import RenameContainer
from utils.checks import check_dm_channel
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")


class RenameModal(discord.ui.Modal, title="Rename Ticket"):
    def __init__(self, bot, ticket: Ticket | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.old_profile: PlayerProfile = ...
        self.new_profile: PlayerProfile = ...

        # Change ticket category related
        self.ticket: Ticket | None = ticket
        self.button: discord.ui.Button | None = None

    old_name = discord.ui.TextInput(
        label="Your in-game name",
        placeholder="nameless tee",
        max_length=15,
        style=discord.TextStyle.short)  # type: ignore
    new_name = discord.ui.TextInput(
        label="The name you'd like to change to",
        placeholder="brainless tee",
        max_length=15,
        style=discord.TextStyle.short)  # type: ignore

    async def check_rename(self) -> (bool, str):
        """|coro|
        Checks the eligibility of a player to rename their in-game name.

        Returns:
            tuple: A tuple containing:
                - bool: True if the rename is allowed, False otherwise.
                - str: An error message if the rename is not allowed, None if it is allowed.
        """

        errors = []
        self.old_profile = await PlayerProfile.from_database(self.bot, self.old_name.value)
        self.new_profile = await PlayerProfile.from_database(self.bot, self.new_name.value)

        # Points check
        if not self.old_profile.points:
            errors.append(
                f'- "{self.old_profile.name}" doesn\'t have any points. Make sure you typed your in-game name correctly.')
        elif self.old_profile.points < 3000:
            errors.append("- Your old name doesn't have enough points. Please read the rename requirements above.")
        if self.new_profile.points and self.new_profile.points > 1000:
            # TODO: if new name has more than 500 points: ask for demos
            errors.append("- The name you'd like to change to is already in use. Please choose a different name.")

        # Check for common team ranks
        if await self.bot.fetch(check_common_teamranks, self.old_profile.name, self.new_profile.name):
            errors.append(
                "- The provided old name and new name have team-ranks in common. Please choose a different new name."
            )

        # Check if the player already renamed within 1 year
        if self.old_profile.next_eligible_rename:
            now = datetime.now()
            if now < self.old_profile.next_eligible_rename:
                next_eligible_date = self.old_profile.next_eligible_rename.date()
                errors.append(
                    f"- You've already received a rename within the last year. "
                    f"You're allowed another rename after `{next_eligible_date}` (`YYYY-MM-DD`)."
                )

        return (
            (False, "\n".join(errors))
            if errors else
            (True, None)
        )

    async def on_submit(self, interaction: discord.Interaction):
        """|coro|
        This function checks if the rename operation is successful. If it fails, an error message is sent to the user.
        If successful, it creates a ticket channel, sends information about the old and new names, and notifies the user of the ticket creation.
        """
        success, err = await self.check_rename()

        if not success:
            await interaction.response.send_message(f"**Rename Failed:**\n{err}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if self.ticket:
            await self.ticket_manager.update_ticket(
                interaction,
                ticket=self.ticket,
                category=TicketCategory.RENAME,
                rename_data=RenameData(old_profile=self.old_profile, new_profile=self.new_profile),
                button=self.button
            )
            return

        ticket = Ticket(
            channel=None,
            creator=interaction.user,
            category=TicketCategory.RENAME,
            rename_data=RenameData(old_profile=self.old_profile, new_profile=self.new_profile),
        )
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=RenameContainer())
        ticket.info_message = await ticket.channel.send(embed=embeds.RenameInfoEmbed(ticket))
        ticket.close_message = await ticket.channel.send(view=CloseContainer.for_category(TicketCategory.RENAME))

        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:**\n"
                        "I wasn't able to send you a DM.\n"
                        "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                        "To fix this, shoot me a message or adjust your privacy settings.\n")
        await interaction.followup.send(content=content, ephemeral=True)

        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a "Rename" ticket (ID: {ticket.channel.id}).'
        )
