# type: ignore
import asyncio
import datetime
import logging
import json
import ipaddress
from datetime import datetime
from typing import Optional

import discord
from discord.ui import Button
from discord.ext import commands

from extensions.ticketsystem import embeds
from extensions.ticketsystem.utils import create_ticket_channel
from extensions.ticketsystem.views import inner_buttons
from extensions.ticketsystem.views.modals import rename_m
from extensions.ticketsystem.views.modals import ban_appeal_m
from extensions.admin.rename import process_rename
from extensions.ticketsystem.manager import Ticket, TicketCategory, TicketState
from extensions.ticketsystem.transcript import TicketTranscript
from constants import Channels, Roles, Emojis
from utils.checks import is_staff, check_dm_channel
from utils.profile import PlayerProfile

log = logging.getLogger("tickets")


class ButtonOnCooldown(commands.CommandError):
    """
    Exception raised when a button is on cooldown.
    Args:
        retry_after (float): The time in seconds until the button can be pressed again.
    """
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


class MainMenu(discord.ui.View):
    """Represents the buttons in the main menu.

    This class provides a user interface for creating various types of tickets,
    such as reports, complaints, and admin mails.

    Args:
        bot: The bot instance used to manage tickets and interactions.
    """

    session = None

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, lambda i: i.user.id)

    async def interaction_check(self, interaction: discord.Interaction):
        if true := self.cooldown.update_rate_limit(interaction):
            await interaction.response.send_message("Hey! Don't spam the buttons.", ephemeral=True)
            return False

        user = interaction.user
        cid = interaction.data.get("custom_id")

        category_map = {
            "MainMenu:report": TicketCategory.REPORT,
            "MainMenu:rename": TicketCategory.RENAME,
            "MainMenu:ban-appeal": TicketCategory.BAN_APPEAL,
            "MainMenu:complaint": TicketCategory.COMPLAINT,
        }

        if cid and (category := category_map.get(cid)):
            if channel := self.ticket_manager.check_for_open_ticket(user, category):
                try:
                    await interaction.client.fetch_channel(channel.id)
                except discord.NotFound:
                    log.warning(f"Initial ticket generation: {channel} no longer exists but still in cache? "
                              f"This can happen if a ticket channel was removed manually or to some HTTPException.")
                    await self.ticket_manager.del_ticket(channel)
                    return True
                except discord.Forbidden as e:
                    await self.bot.get_cog("ErrorHandler").report_interaction_error(
                        interaction,
                        e,
                        note=f"Initial ticket generation: Channel: {channel} exists but I can't access it?"
                    )
                    return False
                except discord.HTTPException as e:
                    await self.bot.get_cog("ErrorHandler").report_interaction_error(
                        interaction,
                        e,
                        note="Unexpected HTTPException during ticket lookup."
                    )
                    return False

                await interaction.response.send_message(
                    content=(
                        f"You already have an open ticket: {channel.mention}\n"
                        "Please resolve or close your existing ticket before creating a new one.\n"
                        "Use `/close` within your existing ticket."
                    ),
                    ephemeral=True,
                )
                return False
        return True

    @discord.ui.button(label="Report", style=discord.ButtonStyle.danger, custom_id="MainMenu:report")
    async def t_reports(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.REPORT, inactivity=0)
        ticket.channel = await create_ticket_channel(interaction, ticket, self.ticket_manager)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.InnerTicketButtons(interaction.client)
        close.update_buttons(ticket)

        message = await ticket.channel.send(
            await self.ticket_manager.mentions(interaction, ticket.category),
            embeds=[embeds.ReportEmbed(interaction.user), embeds.FollowUpEmbed()],
            view=close,
        )

        await message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:**\n"
                        "The bot wasn't able to send you a DM.\n"
                        "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                        "To fix this, send a message to the bot or adjust your privacy settings.\n")
        await interaction.followup.send(content=content, ephemeral=True)

        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a "Report" ticket (ID: {ticket.channel.id}).'
        )

        if interaction.response.is_done():  # noqa
            return

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.blurple, custom_id="MainMenu:rename")
    async def t_renames(self, interaction: discord.Interaction, _: Button):
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, TicketCategory.RENAME):
            await interaction.response.send_message(  # noqa
                content=(
                    f"You already have an open report ticket: {channel.mention} \n"
                    "Please resolve or close your existing ticket before creating a new one. \n"
                    "You can close your ticket using the `/close` command within your existing ticket."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(rename_m.RenameModal(self.bot))  # noqa

    @discord.ui.button(label="Ban Appeal", style=discord.ButtonStyle.blurple, custom_id="MainMenu:ban-appeal")
    async def t_ban_appeal(self, interaction: discord.Interaction, _: Button):  # noqa
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, TicketCategory.BAN_APPEAL):
            await interaction.response.send_message(  # noqa
                content=(
                    f"You already have an open report ticket: {channel.mention} \n"
                    "Please resolve or close your existing ticket before creating a new one. \n"
                    "You can close your ticket using the `/close` command within your existing ticket."
                ),
                ephemeral=True,
            )
            return
        user_locale = str(interaction.locale)
        language = user_locale.split("-")[0]
        await interaction.response.send_modal(
            ban_appeal_m.BanAppealModal(
                self.bot, 
                language=language)
        )

    @discord.ui.button(label="Staff Complaint", style=discord.ButtonStyle.blurple, custom_id="MainMenu:complaint")
    async def t_complaints(self, interaction: discord.Interaction, _: Button):  # noqa
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, TicketCategory.COMPLAINT):
            await interaction.response.send_message(  # noqa
                content=(
                    f"You already have an open report ticket: {channel.mention} \n"
                    "Please resolve or close your existing ticket before creating a new one. \n"
                    "You can close your ticket using the `/close` command within your existing ticket."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.COMPLAINT, inactivity=0)
        ticket.channel = await create_ticket_channel(interaction, ticket, self.ticket_manager)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.InnerTicketButtons(interaction.client)
        close.update_buttons(ticket)

        message = await ticket.channel.send(
            await self.ticket_manager.mentions(interaction, ticket.category),
            embeds=[embeds.ComplaintEmbed(interaction.user), embeds.FollowUpEmbed()],
            view=close,
        )

        await message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:**\n"
                        "I wasn't able to send you a DM.\n"
                        "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                        "To fix this, shoot me a message or adjust your privacy settings.\n")
        await interaction.followup.send(content=content, ephemeral=True)

        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a "Complaint" ticket (ID: {ticket.channel.id}).'
        )

        if interaction.response.is_done():  # noqa
            return

    @discord.ui.button(label="Admin-Mail", style=discord.ButtonStyle.blurple, custom_id="MainMenu:admin-mail")
    async def t_admin_mail(self, interaction: discord.Interaction, _: Button):  # noqa
        if channel := self.ticket_manager.check_for_open_ticket(interaction.user, TicketCategory.ADMIN_MAIL):
            await interaction.response.send_message(  # noqa
                content=(
                    f"You already have an open report ticket: {channel.mention} \n"
                    "Please resolve or close your existing ticket before creating a new one. \n"
                    "You can close your ticket using the `/close` command within your existing ticket."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        ticket = Ticket(channel=None, creator=interaction.user, category=TicketCategory.ADMIN_MAIL, inactivity=0)
        ticket.channel = await create_ticket_channel(interaction, ticket, self.ticket_manager)
        await self.ticket_manager.create_ticket(ticket=ticket, channel=ticket.channel, init=True)

        close = inner_buttons.InnerTicketButtons(interaction.client)
        close.update_buttons(ticket)

        message = await ticket.channel.send(
            await self.ticket_manager.mentions(interaction, ticket.category),
            embeds=[embeds.AdminMailEmbed(interaction.user), embeds.FollowUpEmbed()],
            view=close,
        )

        await message.pin()

        content = f"<@{interaction.user.id}> your ticket has been created: {message.jump_url}"
        if not await check_dm_channel(interaction.user):
            content += ("\n\n**WARNING:**\n"
                        "I wasn't able to send you a DM.\n"
                        "You won't get a transcript or any messages our staff leave after the ticket is closed.\n"
                        "To fix this, shoot me a message or adjust your privacy settings.\n")
        await interaction.followup.send(content=content, ephemeral=True)

        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a "Admin-Mail" ticket (ID: {ticket.channel.id}).'
        )
