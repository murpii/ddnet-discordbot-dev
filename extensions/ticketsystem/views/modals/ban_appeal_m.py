import discord
import logging
from typing import Optional

from extensions.ticketsystem import embeds
from extensions.ticketsystem.lang.ban_appeal_m import ban_appeal_m
from extensions.ticketsystem.views.containers.ban_appeal import BanAppealContainer
from extensions.ticketsystem.views.inner_buttons import BanAppealTicketButtons
from extensions.ticketsystem.manager import Ticket, TicketCategory, AppealData
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
            style=discord.TextStyle.short,
        )
        self.add_item(self.public_ip)

        self.ingame_name = discord.ui.TextInput(
            label=modal["name_label"],
            placeholder=modal["name_label"],
            max_length=15,
            style=discord.TextStyle.short,
        )
        self.add_item(self.ingame_name)

        self.ban_reason = discord.ui.TextInput(
            label=modal["reason_label"],
            placeholder=modal["reason_placeholder"],
            max_length=20,
            style=discord.TextStyle.short,
        )
        self.add_item(self.ban_reason)

        self.appeal = discord.ui.TextInput(
            label=modal["appeal_label"],
            placeholder=modal["appeal_placeholder"],
            max_length=500,
            style=discord.TextStyle.long,
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
        data = AppealData(
            address=self.public_ip.value,
            dnsbl=dnsbl,
            name=self.ingame_name.value,
            reason=self.ban_reason.value,
            appeal=self.appeal.value,
        )

        # This runs if a ticket has changed to a different ticket category.
        if self.ticket:
            ticket = self.ticket
            ticket.appeal_data = data  # update stored data
            ticket.rename_data = []
            await self.ticket_manager.change_ticket(ticket, category=TicketCategory.BAN_APPEAL)

            close = BanAppealTicketButtons(interaction.client)
            close.update_buttons(ticket)

            profile = await PlayerProfile.from_database(self.bot, self.ingame_name.value)

            await ticket.start_message.edit(view=BanAppealContainer(ticket))
            await ticket.info_message.edit(embed=embeds.BanAppealInfoEmbed(ticket, profile))
            await ticket.close_message.edit(embed=embeds.FollowUpEmbed(), view=close)

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
            category=TicketCategory.BAN_APPEAL,
            appeal_data=data,
        )

        ticket.channel = await self.ticket_manager.create_channel(interaction, ticket)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel)

        close = BanAppealTicketButtons(interaction.client)
        close.update_buttons(ticket)
        profile = await PlayerProfile.from_database(self.bot, self.ingame_name.value)

        ticket.start_message = await ticket.channel.send(
            # content=f"Alerts:{await self.ticket_manager.mentions(interaction, ticket.category)}",
            # embed=embeds.BanAppealEmbed(interaction.user),
            view=BanAppealContainer(ticket),
        )
        ticket.info_message = await ticket.channel.send(embed=embeds.BanAppealInfoEmbed(ticket, profile))
        ticket.close_message = await ticket.channel.send(embed=embeds.FollowUpEmbed(), view=close)
        await ticket.start_message.pin()

        await interaction.followup.send(
            content=f"<@{interaction.user.id}> your ticket has been created: {ticket.start_message.jump_url}",
            ephemeral=True,
        )
