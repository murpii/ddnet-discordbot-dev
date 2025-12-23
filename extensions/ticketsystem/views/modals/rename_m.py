import discord
import datetime
from datetime import datetime
import logging

from extensions.ticketsystem import embeds
from extensions.ticketsystem.queries import check_common_teamranks
from extensions.ticketsystem.manager import Ticket, TicketCategory
from extensions.ticketsystem.views.containers.rename import RenameContainer
from extensions.ticketsystem.views.inner_buttons import RenameTicketButtons
from utils.checks import check_dm_channel
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")


class RenameModal(discord.ui.Modal, title="Rename Ticket"):
    def __init__(self, bot, ticket: Ticket | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.profile_old: PlayerProfile = ...
        self.profile_new: PlayerProfile = ...

        # Change ticket category related
        self.ticket: Ticket | None = ticket
        self.button: discord.ui.Button | None = None

    old_name = discord.ui.TextInput(
        label="Your in-game name",
        placeholder="nameless tee",
        max_length=15,
        style=discord.TextStyle.short)
    new_name = discord.ui.TextInput(
        label="The name you'd like to change to",
        placeholder="brainless tee",
        max_length=15,
        style=discord.TextStyle.short)

    async def check_rename(self) -> (bool, str):
        """|coro|
        Checks the eligibility of a player to rename their in-game name.

        Returns:
            tuple: A tuple containing:
                - bool: True if the rename is allowed, False otherwise.
                - str: An error message if the rename is not allowed, None if it is allowed.
        """

        errors = []
        self.profile_old = await PlayerProfile.from_database(self.bot, self.old_name.value)
        self.profile_new = await PlayerProfile.from_database(self.bot, self.new_name.value)

        # Points check
        if not self.profile_old.points:
            errors.append(
                f'- "{self.profile_old.name}" doesn\'t have any points. Make sure you typed your in-game name correctly.')
        elif self.profile_old.points < 3000:
            errors.append("- Your old name doesn't have enough points. Please read the rename requirements above.")
        if self.profile_new.points and self.profile_new.points > 1000:
            # TODO: if new name has more than 500 points: ask for demos
            errors.append("- The name you'd like to change to is already in use. Please choose a different name.")

        # Check for common team ranks
        if await self.bot.fetch(check_common_teamranks, self.profile_old.name, self.profile_new.name):
            errors.append(
                "- The provided old name and new name have team-ranks in common. Please choose a different new name."
            )

        # Check if the player already renamed within 1 year
        if self.profile_old.next_eligible_rename:
            now = datetime.now()
            if now < self.profile_old.next_eligible_rename:
                next_eligible_date = self.profile_old.next_eligible_rename.date()
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
            ticket = self.ticket
            ticket.rename_data = [self.profile_old, self.profile_new]
            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.RENAME)

            inner_view = RenameTicketButtons(interaction.client)
            inner_view.update_buttons(ticket)

            await ticket.start_message.edit(content=None, embeds=[], view=RenameContainer())
            await ticket.info_message.edit(embed=embeds.RenameInfoEmbed(self.profile_old, self.profile_new))
            await ticket.close_message.edit(embed=embeds.FollowUpEmbed(), view=inner_view)

            await self.ticket_manager.set_lock(ticket, ticket.locked)
            overwrites = ticket.get_overwrites(interaction)
            await ticket.channel.edit(
                name=f"{ticket.category.value}-{await self.ticket_manager.ticket_num(category=ticket.category.value)}",
                overwrites=overwrites
            )

            self.button.disabled = True
            await interaction.message.edit(view=self.button.view)

            await interaction.channel.send(
                f"{ticket.creator.mention} ticket channel category changed to **{ticket.category.name}**. "
                f"Kindly review {ticket.start_message.jump_url}.",
            )
            await interaction.delete_original_response()
            await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)
            return

        ticket = Ticket(
            channel=None,
            creator=interaction.user,
            category=TicketCategory.RENAME,
            rename_data=[self.profile_old, self.profile_new],
        )
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        inner_view = RenameTicketButtons(interaction.client)
        inner_view.update_buttons(ticket)

        ticket.start_message = await ticket.channel.send(view=RenameContainer())
        ticket.info_message = await ticket.channel.send(
            embed=embeds.RenameInfoEmbed(self.profile_old, self.profile_new))
        ticket.close_message = await ticket.channel.send(embed=embeds.FollowUpEmbed(), view=inner_view)

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
