import logging
import discord

from extensions.ticketsystem import embeds
from extensions.ticketsystem.views import modals as rename_m
from extensions.ticketsystem.views.containers.admin_mail import AdminMailContainer
from extensions.ticketsystem.views.containers.close import CloseContainer
from extensions.ticketsystem.views.containers.community_app import CommunityAppContainer
from extensions.ticketsystem.views.containers.complaint import ComplaintContainer
from extensions.ticketsystem.views.containers.report import ReportContainer
from extensions.ticketsystem.views.modals import ban_appeal_m, rename_m
from extensions.ticketsystem.ticket import Ticket, TicketCategory
from utils.checks import check_dm_channel

log = logging.getLogger("tickets")


class ReportButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.REPORT.value):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id="MainMenu:report",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.REPORT):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.REPORT)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=ReportContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.ReportInfoEmbed(interaction.guild))
        ticket.close_message = await ticket.channel.send(
            # embed=embeds.FollowUpEmbed(),
            # view=inner_buttons.ReportTicketButtons(interaction.client)
            view=CloseContainer.for_category(TicketCategory.REPORT)
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
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:rename",
        )
        self.bot = bot
        self.ticket = ticket
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.RENAME):
            return

        modal = rename_m.RenameModal(self.bot, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class BanAppealButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.RENAME.value, ticket=None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # type: ignore
            custom_id="MainMenu:ban-appeal",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.BAN_APPEAL):
            return

        language = str(interaction.locale).split("-")[0]
        modal = ban_appeal_m.BanAppealModal(self.bot, language=language, ticket=self.ticket)
        modal.button = self
        await interaction.response.send_modal(modal)


class ComplaintButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.COMPLAINT.value):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="MainMenu:complaint",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.COMPLAINT):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.COMPLAINT)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=ComplaintContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.ComplaintInfoEmbed(ticket))
        ticket.close_message = await ticket.channel.send(
            # embed=embeds.FollowUpEmbed(),
            # view=close
            view=CloseContainer.for_category(TicketCategory.COMPLAINT)
        )
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += "\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages."
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created a "Complaint" ticket (ID: {ticket.channel.id}).')


class AdminMailButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.ADMIN_MAIL.value):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="MainMenu:admin-mail",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.ADMIN_MAIL):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.ADMIN_MAIL)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=AdminMailContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.AdminMailInfoEmbed())
        ticket.close_message = await ticket.channel.send(
            # embed=embeds.FollowUpEmbed(),
            # view=close
            view=CloseContainer.for_category(TicketCategory.ADMIN_MAIL)
        )
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += "\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages."
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created an "Admin-Mail" ticket (ID: {ticket.channel.id}).')


class CommunityAppButton(discord.ui.Button):
    def __init__(self, bot, label: str = TicketCategory.COMMUNITY_APP.value):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="MainMenu:community-app",
        )
        self.bot = bot
        self.ticket_manager = bot.ticket_manager

    async def callback(self, interaction: discord.Interaction):
        if await self.ticket_manager.check_for_open_ticket(interaction, TicketCategory.COMMUNITY_APP):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.COMMUNITY_APP)
        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        ticket.start_message = await ticket.channel.send(view=CommunityAppContainer(ticket))
        ticket.info_message = await ticket.channel.send(embed=embeds.AdminMailInfoEmbed())
        ticket.close_message = await ticket.channel.send(
            # embed=embeds.FollowUpEmbed(),
            # view=close
            view=CloseContainer.for_category(TicketCategory.COMMUNITY_APP)
        )
        await ticket.start_message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += "\n\n**WARNING:** DMs are blocked, so you won't get transcripts or closure messages."
        await interaction.followup.send(content=content, ephemeral=True)
        log.info(f'{interaction.user} created an "Community Application" ticket (ID: {ticket.channel.id}).')
