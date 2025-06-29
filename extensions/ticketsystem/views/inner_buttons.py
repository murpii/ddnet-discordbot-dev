from datetime import datetime, timedelta, timezone
import json
import logging
import asyncio
import re
from configparser import ConfigParser
import discord
from discord.ui import Button

from extensions.ticketsystem.views.confirm import ConfirmViewStaff, ConfirmView
from extensions.ticketsystem.manager import TicketCategory, TicketState
from extensions.admin.rename import process_rename
from utils.text import str_to_timedelta, strip_surrounding_quotes, to_discord_timestamp
from utils.checks import is_staff
from utils.regex import BAN_REF_RE, BAN_RE
from constants import Roles, Channels

log = logging.getLogger("tickets")
config = ConfigParser()
config.read("config.ini")


class InnerTicketButtons(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_manager = bot.ticket_manager
        self.click_count = 0
        self.scores = {}
        self.lock = asyncio.Lock()

    def update_buttons(self, ticket):
        self.clear_items()
        self.add_item(self.t_close)
        self.add_item(self.t_lock)

        if ticket.category == TicketCategory.RENAME:
            self.add_item(self.t_process_rename)
            self.add_item(self.t_print_rename)
        elif ticket.category == TicketCategory.BAN_APPEAL:
            self.add_item(self.t_appeal_find_ban)
        elif ticket.category == TicketCategory.REPORT and ticket.state != TicketState.CLAIMED:
            self.add_item(self.t_moderator_check)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.blurple, custom_id="MainMenu:close_ticket")
    async def t_close(self, interaction: discord.Interaction, _: Button):
        """The close button found below a tickets embed message"""

        options = ConfirmViewStaff \
            if is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]) \
            else ConfirmView

        message = ("Are you sure you want to close the ticket?\n"
            "Closing a ticket due to **neglect** will automatically send a apology message to the ticket creator.\n"
            "Closing a ticket for **inactivity** alerts the creator that it was closed for that reason.") \
            if is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]) \
            else "Are you sure you want to close the ticket?"

        await interaction.response.send_message(
            content=message,
            ephemeral=True,
            view=options(self.bot)
        )

    @discord.ui.button(
        label="Print CMD",
        style=discord.ButtonStyle.blurple,
        custom_id="RenameCMDButton"
    )
    async def t_print_rename(self, interaction: discord.Interaction, _: Button):
        if not is_staff(interaction.user, roles=[Roles.ADMIN]):
            await interaction.response.send_message(
                "Only Administrators are allowed to use this button.",
                ephemeral=True
            )
            return

        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        if not ticket.rename_data:
            await interaction.response.send_message("Could not fetch names for rename.", ephemeral=True)
            return
        else:
            old = ticket.rename_data[0].name
            new = ticket.rename_data[1].name
            await interaction.response.send_message(
                content=f"```sh\n"
                f"servers/scripts/player-rename.sh \"{old}\" \"{new}\" \"{interaction.user.name}\" "
                f"| mysql -u {config["DATABASE"]["MARIADB_USER"]} -p'{config["DATABASE"]["MARIADB_PASSWORD"]}' teeworlds"
                f"```",
                ephemeral=True
            )

    @discord.ui.button(
        label="Run Rename",
        style=discord.ButtonStyle.red,
        custom_id="RenameButton"
    )
    async def t_process_rename(self, interaction: discord.Interaction, _: Button):
        if not is_staff(interaction.user, roles=[Roles.ADMIN]):
            await interaction.response.send_message(
                "Only Administrators are allowed to use this button.",
                ephemeral=True
            )
            return

        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        try:
            if not ticket.rename_data[0] or not ticket.rename_data[1]:
                await interaction.response.send_message("BUG: Could not fetch names for rename.")
                return
            else:
                await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
                await process_rename(self.bot, interaction, ticket.rename_data[0].name, ticket.rename_data[1].name)
        except Exception as e:
            try:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                return
            except discord.InteractionResponded:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)
                return

    @discord.ui.button(
        label="🔒 Lock Ticket",
        style=discord.ButtonStyle.gray,
        custom_id="LockButton"
    )
    async def t_lock(self, interaction: discord.Interaction, button: Button):
        """Locks/Unlocks the ticket channel for the creator."""
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        lock_status = not ticket.locked
        await interaction.channel.set_permissions(ticket.creator, send_messages=not lock_status)
        button.label = "🔓 Unlock Ticket" if lock_status else "🔒 Lock Ticket"
        ticket.locked = lock_status
        await self.bot.ticket_manager.set_lock(ticket, lock_status)

        self.update_buttons(ticket)
        await interaction.message.edit(view=self)

        await ticket.channel.send(
            content=f"The ticket has been {'locked' if lock_status else 'unlocked'}.",
        )

        await interaction.response.send_message(
            content=f"The ticket has been {'locked' if lock_status else 'unlocked'}. "
                    f"OP {'can\'t' if lock_status else 'can'} send further messages.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Find Ban",
        style=discord.ButtonStyle.red,  # type: ignore
        custom_id="FindBan")
    async def t_appeal_find_ban(self, interaction: discord.Interaction, button: Button):
        if not is_staff(
            interaction.user,
            roles=[
                Roles.ADMIN,
                Roles.DISCORD_MODERATOR,
                Roles.MODERATOR
            ]
        ):
            await interaction.response.send_message("Only staff members are allowed to use this button.")

        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        if not ticket.appeal_data or not ticket.appeal_data.address:
            await interaction.response.send_message("No address found.", ephemeral=True)
            return

        messages = []
        await interaction.response.defer(ephemeral=True, thinking=True)
        async for msg in self.bot.get_channel(Channels.BANS).history(limit=1000, oldest_first=False):
            if f"`{ticket.appeal_data.address}`" in msg.content:
                messages.append(msg)

        if not messages:
            await interaction.edit_original_response(content="Unable to find ban message.")
            return

        now = datetime.now(timezone.utc)
        string = f"{'One ban' if len(messages) == 1 else 'Multiple bans'} found for IP `{ticket.appeal_data.address}`:\n"
        last_name = None
        for message in messages:
            regex = re.match(BAN_RE, message.content)
            if not regex:
                continue

            try:
                dt = datetime.strptime(regex['timestamp'], "%Y-%m-%d %H:%M:%S")
                ban_duration_td = to_discord_timestamp(dt, style='R')
            except ValueError:
                ban_duration_td = None

            if ban_duration_td:
                expired = now > dt.replace(tzinfo=timezone.utc)
                expiry_info = (
                    "**Expired**" if expired else f"**Expires:** {ban_duration_td}"
                )
            else:
                expiry_info = "ERROR"

            try:
                ref_message = await message.channel.fetch_message(message.reference.message_id)
                regex_ref = re.match(BAN_REF_RE, ref_message.content)
                reason = regex_ref['reason'].strip()
            except discord.NotFound:
                reason = "Unknown"

            author = message.author.mention
            name = strip_surrounding_quotes(regex['banned_user'] or '').strip()

            if name != last_name:
                string += f"{name}:\n"
                last_name = name

            string += (f"    {reason}  "
                       f"Banned by: {author}  "
                       f"{expiry_info}  "
                       f"({message.jump_url})\n")

        if string.strip() == f"{'One ban' if len(messages) == 1 else 'Multiple bans'} found for IP `{ticket.appeal_data.address}`:":
            await interaction.edit_original_response(content="Could not find any ban message.")
        else:
            await interaction.edit_original_response(content=string)

    @discord.ui.button(
        label="Claim (For Moderators)",
        style=discord.ButtonStyle.red,
        custom_id="ModeratorButton")
    async def t_moderator_check(self, interaction: discord.Interaction, button: Button):
        if is_staff(
            interaction.user,
            roles=[
                Roles.ADMIN,
                Roles.DISCORD_MODERATOR,
                Roles.MODERATOR
            ]
        ):
            ticket = await self.ticket_manager.get_ticket(interaction.channel)
            if ticket.state == TicketState.CLAIMED:
                await interaction.response.send_message(  # noqa
                    content="This ticket has already been claimed by someone else.",
                    ephemeral=True
                )
                return

            async with self.lock:
                await ticket.set_state(state=TicketState.CLAIMED)
                button.disabled = True
                button.label = "Claimed"

                self.update_buttons(ticket)
                await interaction.message.edit(view=self)
                log.info(
                    f'{interaction.user} (ID: {interaction.user.id}) claimed ticket named {interaction.channel.name}.'
                )

                score_file = "data/ticket-system/scores.json"
                with open(score_file, "r", encoding="utf-8") as file:
                    self.scores = json.load(file)

                user_id = str(interaction.user.id)
                if user_id in self.scores:
                    self.scores[user_id] += 1
                else:
                    self.scores[user_id] = 1

                with open(score_file, "w", encoding="utf-8") as file:
                    json.dump(self.scores, file)  # noqa

            await interaction.response.send_message(  # noqa
                content=f"{interaction.user.mention}, thanks for taking care of this! Increased your score by 1.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=False),
            )

            await interaction.channel.send(
                content=(
                    f"Hey, {interaction.user.mention} is on their way to help you with your report. "
                    "Thank you for your patience!"
                ),
                allowed_mentions=discord.AllowedMentions(users=False),
            )
        else:
            # don't judge.
            responses = {
                1: "This button is for moderators only! DO NOT click me again!",
                2: "Stop clicking me!",
                3: "If you won't stop, I'll close your ticket, last warning!",
                4: ":triumph: You did not just do that!",
                5: "(╯°□°)╯︵ ┻━┻",
                6: "┬─┬ノ( º _ ºノ)"
            }
            self.click_count += 1

            if self.click_count in responses:
                await interaction.response.send_message(  # noqa
                    content=responses[self.click_count],
                    ephemeral=True
                )

            if self.click_count == 6:
                self.click_count = 4
