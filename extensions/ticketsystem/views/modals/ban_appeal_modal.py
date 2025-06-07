import discord
import logging
from typing import Optional

from extensions.ticketsystem import embeds
from extensions.ticketsystem.lang.ban_appeal_modal import BAN_APPEAL_MODAL, BAN_APPEAL_CLOUDFLARE
from extensions.ticketsystem.views.inner_buttons import InnerTicketButtons
from extensions.ticketsystem.utils import create_ticket_channel
from extensions.ticketsystem.manager import Ticket, TicketCategory, AppealData
from utils.checks import check_dm_channel, check_public_ip, check_ip
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")


class BanAppealModal(discord.ui.Modal, title="Ban Appeal Ticket"):
    session = None
    def __init__(self, bot, language="en"):
        self.bot = bot
        self.language = language
        self.ticket_manager = bot.ticket_manager
        self.api_key = self.bot.config.get("DNSBL_API", "KEY")
        self.is_blocked: Optional[str] = None
        modal = BAN_APPEAL_MODAL.get(language, BAN_APPEAL_MODAL["en"])
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
            style=discord.TextStyle.short)
        self.add_item(self.ingame_name)

        self.ban_reason = discord.ui.TextInput(
            label=modal["reason_label"],
            placeholder=modal["reason_placeholder"],
            max_length=20,
            style=discord.TextStyle.short)
        self.add_item(self.ban_reason)

        self.appeal = discord.ui.TextInput(
            label=modal["appeal_label"],
            placeholder=modal["appeal_placeholder"],
            max_length=500,
            style=discord.TextStyle.long)
        self.add_item(self.appeal)

    async def on_submit(self, interaction: discord.Interaction):
        success, message = check_public_ip(self.public_ip.value)
        if not success:
            await interaction.response.send_message(  # noqa
                f"**IP Check Failed:**\n{message}\n\n"
                f"**Your provided reason:**\n{self.ban_reason}",
                ephemeral=True
            )
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
            dnsbl, cloudflare = await check_ip(self.public_ip.value, self.session, self.api_key)
            data = AppealData(
                address=self.public_ip.value, 
                dnsbl=dnsbl, 
                name=self.ingame_name.value, 
                reason=self.ban_reason.value, 
                appeal=self.appeal.value
            )
            ticket = Ticket(
                channel=None,
                creator=interaction.user,
                category=TicketCategory.BAN_APPEAL,
                appeal_data=data,
                inactivity=0
            )
            ticket.channel = await create_ticket_channel(interaction, ticket, self.ticket_manager)

            await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel)

            message = await ticket.channel.send(
                content=f"Alerts:{await self.ticket_manager.mentions(interaction, ticket.category)}",
                embed=embeds.BanAppealEmbed(interaction.user)
            )

            close = InnerTicketButtons(interaction.client)
            close.update_buttons(ticket)
            profile = await PlayerProfile.from_database(self.bot, self.ingame_name.value)
            msg = await ticket.channel.send(
                embeds=[
                    embeds.BanAppealInfoEmbed(ticket, profile),
                    embeds.FollowUpEmbed()
                ],
                view=close)
            await msg.pin()

            cloudflare = BAN_APPEAL_CLOUDFLARE.get(self.language, BAN_APPEAL_CLOUDFLARE["en"])
            
            content = f"<@{interaction.user.id}> your ticket has been created: {message.jump_url}"
            if not await check_dm_channel(interaction.user):
                content += ("\n\n**WARNING:**\n"
                            "I wasn't able to send you a DM.\n"
                            "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                            "To fix this, shoot me a message or adjust your privacy settings.\n")
            await interaction.followup.send(content=content, ephemeral=True)

            if cloudflare:
                cloudflare_em = discord.Embed(
                    title="Cloudflare",
                    colour=discord.Color.red(),
                    description=f"{ticket.creator.mention} {cloudflare["description"]}"
                )
                cloudflare_em.add_field(
                    name=cloudflare["title"],
                    value=f"[{cloudflare["value"]}]"
                          "(https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/remove-warp/)",
                )
                await ticket.channel.send(embed=cloudflare_em)

            log.info(
                f'{interaction.user} (ID: {interaction.user.id}) created a "Ban Appeal" ticket (ID: {ticket.channel.id}).'
            )