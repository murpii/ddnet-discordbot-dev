import contextlib
import discord
from datetime import datetime

from extensions.ticketsystem.channel import build_ticket_channel
from extensions.ticketsystem.queries import check_common_teamranks
from extensions.ticketsystem.ticket import Ticket, TicketCategory, RenameData
from utils.profile import PlayerProfile


class RenameModal(discord.ui.Modal, title="Rename Ticket"):
    def __init__(self, bot, ticket: Ticket | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.old_profile: PlayerProfile = ...
        self.new_profile: PlayerProfile = ...

        # change ticket category related
        self.ticket: Ticket | None = ticket
        self.button: discord.ui.Button | None = None
        self.origin_message: discord.Message | None = None

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

    # TODO: Include gate here as well
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

        # check for common team ranks
        if await self.bot.fetch(check_common_teamranks, self.old_profile.name, self.new_profile.name):
            errors.append(
                "- The provided old name and new name have team-ranks in common. Please choose a different new name."
            )

        # check if the player already renamed within 1 year
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
        """Handle the submission of the rename modal and process the rename ticket.
        Validates the rename request, updates an existing ticket, or creates a new rename ticket channel.

        Args:
            interaction: The interaction created when the modal is submitted.
        """
        success, err = await self.check_rename()

        if not success:
            await interaction.response.send_message(f"**Rename Failed:**\n{err}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        # Case: A Ticket channel already exists and is being updated
        if self.ticket:
            await self.ticket_manager.update_ticket(
                interaction,
                ticket=self.ticket,
                category=TicketCategory.RENAME,
                rename_data=RenameData(old_profile=self.old_profile, new_profile=self.new_profile),
                button=self.button
            )
            if self.origin_message:
                with contextlib.suppress(discord.NotFound):
                    await self.origin_message.delete()
            return

        ticket = Ticket(
            channel=None,
            creator=interaction.user,
            category=TicketCategory.RENAME,
            rename_data=RenameData(old_profile=self.old_profile, new_profile=self.new_profile),
        )
        await build_ticket_channel(interaction, ticket)
