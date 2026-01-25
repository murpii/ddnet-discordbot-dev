import discord
import logging
from typing import Optional

from extensions.ticketsystem import embeds
from extensions.ticketsystem.lang.ban_appeal_m import ban_appeal_m
from extensions.ticketsystem.views.containers.ban_appeal import BanAppealContainer
from extensions.ticketsystem.views.containers.close import CloseContainer
from extensions.ticketsystem.ticket import Ticket, AppealData, TicketCategory
from utils.checks import check_public_ip, check_ip
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")


class BanAppealModal(discord.ui.Modal, title="Ban Appeal Ticket"):
    session = None

    def __init__(self, bot, language="en", ticket: Ticket | None = None):
        self.bot = bot
        self.language = language
        self.ticket_manager = bot.ticket_manager
        self.api_key = self.bot.config.get("DNSBL_API", "KEY")
        self.is_blocked: Optional[str] = None
        self.button: discord.ui.Button | None = None

        # Change ticket category related
        self.ticket: Ticket | None = ticket

        modal = ban_appeal_m.get(language, ban_appeal_m["en"])
        super().__init__(title=modal["title"], timeout=None)

        self.public_ip = discord.ui.TextInput(
            label=modal["ip_label"],
            placeholder=modal["ip_placeholder"],
            max_length=15,
            style=discord.TextStyle.short,  # type: ignore
        )
        self.add_item(self.public_ip)

        self.ingame_name = discord.ui.TextInput(
            label=modal["name_label"],
            placeholder=modal["name_label"],
            max_length=15,
            style=discord.TextStyle.short,  # type: ignore
        )
        self.add_item(self.ingame_name)

        self.ban_reason = discord.ui.TextInput(
            label=modal["reason_label"],
            placeholder=modal["reason_placeholder"],
            max_length=20,
            style=discord.TextStyle.short,  # type: ignore
        )
        self.add_item(self.ban_reason)

        self.appeal = discord.ui.TextInput(
            label=modal["appeal_label"],
            placeholder=modal["appeal_placeholder"],
            max_length=500,
            style=discord.TextStyle.long,  # type: ignore
        )
        self.add_item(self.appeal)

    async def on_submit(self, interaction: discord.Interaction):
        success, message = check_public_ip(self.public_ip.value)
        if not success:
            await interaction.response.send_message(
                f"**IP Check Failed:**\n{message}\n\n"
                f"**Your provided reason:**\n{self.ban_reason}",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        dnsbl, cloudflare = await check_ip(self.public_ip.value, self.session, self.api_key)
        profile = await PlayerProfile.from_database(self.bot, self.ingame_name.value)
        data = AppealData(
            address=self.public_ip.value,
            dnsbl=dnsbl,
            name=self.ingame_name.value,
            reason=self.ban_reason.value,
            appeal=self.appeal.value,
            profile=profile
        )

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            await self.ticket_manager.update_ticket(
                interaction,
                ticket=self.ticket,
                category=TicketCategory.BAN_APPEAL,
                appeal_data=data,
                # close_view=close_view,
                # close_view=CloseContainer(interaction.client, self.ticket),
                button=self.button
            )
            return

        ticket = Ticket(
            channel=None,
            creator=interaction.user,
            category=TicketCategory.BAN_APPEAL,
            appeal_data=data,
        )

        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel)

        ticket.start_message = await ticket.channel.send(
            # content=f"Alerts:{await self.ticket_manager.mentions(interaction, ticket.category)}",
            # embed=embeds.BanAppealEmbed(interaction.user),
            view=BanAppealContainer(ticket),
        )
        ticket.info_message = await ticket.channel.send(embed=embeds.BanAppealInfoEmbed(ticket, profile))
        ticket.close_message = await ticket.channel.send(
            # embed=embeds.FollowUpEmbed(),
            # view=close
            view=CloseContainer.for_category(TicketCategory.BAN_APPEAL)
        )
        await ticket.start_message.pin()

        await interaction.followup.send(
            content=f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}",
            ephemeral=True,
        )
