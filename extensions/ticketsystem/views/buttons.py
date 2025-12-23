import logging
import discord
from discord.ext import commands

from extensions.ticketsystem import embeds
from extensions.ticketsystem.embeds.admin_mail import AdminMailInfoEmbed
from extensions.ticketsystem.views import inner_buttons, modals as rename_m
from extensions.ticketsystem.views.containers.admin_mail import AdminMailContainer
from extensions.ticketsystem.views.containers.community_app import CommunityAppContainer
from extensions.ticketsystem.views.containers.complaint import ComplaintContainer
from extensions.ticketsystem.views.containers.report import ReportContainer
from extensions.ticketsystem.views.modals import ban_appeal_m, rename_m
from extensions.ticketsystem.manager import Ticket, TicketCategory
from utils.checks import check_dm_channel

log = logging.getLogger("tickets")


class ReportButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.REPORT.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id="MainMenu:report",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            ticket = self.ticket
            ticket.rename_data = []
            ticket.appeal_data = None

            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.REPORT)

            await ticket.start_message.edit(view=ReportContainer(ticket))
            await ticket.info_message.edit(embed=embeds.ReportInfoEmbed())
            await ticket.close_message.edit(
                embed=embeds.FollowUpEmbed(),
                view=inner_buttons.ReportTicketButtons(interaction.client)
            )

            await self.ticket_manager.set_lock(ticket, ticket.locked)
            overwrites = ticket.get_overwrites(interaction)
            await ticket.channel.edit(
                name=f"{ticket.category.value}-{await self.ticket_manager.ticket_num(category=ticket.category.value)}",
                overwrites=overwrites
            )

            await interaction.channel.send(
                f"{ticket.creator.mention} ticket channel category changed to **{ticket.category.name}**. "
                f"Kindly review {ticket.start_message.jump_url}.",
            )
            await interaction.delete_original_response()
            await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)
            return

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.REPORT)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=ReportContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.ReportInfoEmbed())
        ticket.close_message = await ticket.channel.send(
            embed=embeds.FollowUpEmbed(),
            view=inner_buttons.ReportTicketButtons(interaction.client)
        )
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += (
                "\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages."
            )
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created a "Report" ticket (ID: {ticket.channel.id}).')


class RenameButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.RENAME.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id="MainMenu:rename",
        )
        self.bot = bot
        self.ticket = ticket
        self.ticket_manager = bot.ticket_manager

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        modal = rename_m.RenameModal(self.bot, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class BanAppealButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.RENAME.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id="MainMenu:ban-appeal",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        language = str(interaction.locale).split("-")[0]
        modal = ban_appeal_m.BanAppealModal(self.bot, language=language, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class ComplaintButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.COMPLAINT.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id="MainMenu:complaint",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            ticket = self.ticket
            ticket.rename_data = []
            ticket.appeal_data = None

            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.COMPLAINT)

            await ticket.start_message.edit(view=ComplaintContainer(ticket))
            await ticket.info_message.edit(embed=embeds.ComplaintInfoEmbed(ticket))
            await ticket.close_message.edit(
                embed=embeds.FollowUpEmbed(),
                view=inner_buttons.BaseTicketButtons(interaction.client)
            )

            await self.ticket_manager.set_lock(ticket, ticket.locked)
            overwrites = ticket.get_overwrites(interaction)
            await ticket.channel.edit(
                name=f"{ticket.category.value}-{await self.ticket_manager.ticket_num(category=ticket.category.value)}",
                overwrites=overwrites
            )

            await interaction.channel.send(
                f"{ticket.creator.mention} ticket channel category changed to **{ticket.category.name}**. "
                f"Kindly review {ticket.start_message.jump_url}.",
            )
            await interaction.delete_original_response()
            await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)
            return

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.COMPLAINT)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.BaseTicketButtons(interaction.client)
        close.update_buttons(ticket)

        ticket.start_message = await ticket.channel.send(view=ComplaintContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.ComplaintInfoEmbed(ticket))
        ticket.close_message = await ticket.channel.send(embed=embeds.FollowUpEmbed(), view=close)
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages.")
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created a "Complaint" ticket (ID: {ticket.channel.id}).')


class AdminMailButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.ADMIN_MAIL.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id="MainMenu:admin-mail",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            ticket = self.ticket
            ticket.rename_data = []
            ticket.appeal_data = None

            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.ADMIN_MAIL)

            await ticket.start_message.edit(view=AdminMailContainer(ticket))
            await ticket.info_message.edit(embed=embeds.AdminMailInfoEmbed())
            await ticket.close_message.edit(
                embed=embeds.FollowUpEmbed(),
                view=inner_buttons.BaseTicketButtons(interaction.client)
            )

            await self.ticket_manager.set_lock(ticket, ticket.locked)
            overwrites = ticket.get_overwrites(interaction)
            await ticket.channel.edit(
                name=f"{ticket.category.value}-{await self.ticket_manager.ticket_num(category=ticket.category.value)}",
                overwrites=overwrites
            )

            await interaction.channel.send(
                f"{ticket.creator.mention} ticket channel category changed to **{ticket.category.name}**. "
                f"Kindly review {ticket.start_message.jump_url}.",
            )
            await interaction.delete_original_response()
            await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)
            return

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.ADMIN_MAIL)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.BaseTicketButtons(interaction.client)
        close.update_buttons(ticket)

        ticket.start_message = await ticket.channel.send(view=AdminMailContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.AdminMailInfoEmbed())
        ticket.close_message = await ticket.channel.send(embed=embeds.FollowUpEmbed(), view=close)
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages.")
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created an "Admin-Mail" ticket (ID: {ticket.channel.id}).')


class CommunityAppButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.COMMUNITY_APP.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id="MainMenu:community-app",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def has_open_ticket(self, interaction: discord.Interaction, category: TicketCategory) -> bool:
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, category):
            await interaction.response.send_message(
                f"You already have an open ticket: {channel.mention}\n"
                "Please resolve or close your existing ticket before creating a new one.\n"
                "Use `/close` within your existing ticket.",
                ephemeral=True,
            )
            return True
        return False

    async def callback(self, interaction: discord.Interaction):
        if await self.has_open_ticket(interaction, TicketCategory.COMMUNITY_APP):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            ticket = self.ticket
            ticket.rename_data = []
            ticket.appeal_data = None

            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.COMMUNITY_APP)

            await ticket.start_message.edit(view=CommunityAppContainer(ticket))
            await ticket.info_message.edit(embed=embeds.AdminMailInfoEmbed())
            await ticket.close_message.edit(
                embed=embeds.FollowUpEmbed(),
                view=inner_buttons.BaseTicketButtons(interaction.client)
            )

            await self.ticket_manager.set_lock(ticket, ticket.locked)
            overwrites = ticket.get_overwrites(interaction)
            await ticket.channel.edit(
                name=f"{ticket.category.value}-{await self.ticket_manager.ticket_num(category=ticket.category.value)}",
                overwrites=overwrites
            )

            await interaction.channel.send(
                f"{ticket.creator.mention} ticket channel category changed to **{ticket.category.name}**. "
                f"Kindly review {ticket.start_message.jump_url}.",
            )
            await interaction.delete_original_response()
            await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False, force_state=False)
            return

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.COMMUNITY_APP)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.BaseTicketButtons(interaction.client)
        close.update_buttons(ticket)

        ticket.start_message = await ticket.channel.send(view=CommunityAppContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.AdminMailInfoEmbed())
        ticket.close_message = await ticket.channel.send(embed=embeds.FollowUpEmbed(), view=close)
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages.")
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created an "Community Application" ticket (ID: {ticket.channel.id}).')
