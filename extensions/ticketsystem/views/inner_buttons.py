import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ui import button

from constants import Roles, Channels
from extensions.admin.rename import process_rename
from extensions.ticketsystem.ticket import TicketState
from extensions.ticketsystem.views.confirm import ConfirmViewStaff, ConfirmView
from bot import config
from utils.checks import is_staff
from utils.misc import ip_matches
from utils.text import to_discord_timestamp, strip_surrounding_quotes

log = logging.getLogger("tickets")

BAN_RE = (
    r"(?P<author>\w+) banned (?P<banned_user>.+?) "
    r"`(?P<ip_range>\d{1,3}(?:\.\d{1,3}){3}(?:-\d{1,3}(?:\.\d{1,3}){3})?)` "
    r"for `(?P<reason>.+?)` until (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)


class CloseBtn(discord.ui.Button):
    def __init__(self, label: str = "Close"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:CloseBtn",
        )

    async def callback(self, interaction: discord.Interaction):
        options = ConfirmViewStaff if is_staff(
            interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]
        ) else ConfirmView

        message = (
            "Are you sure you want to close the ticket?\n"
            "Closing due to **neglect** will send an apology to the creator.\n"
            "Closing for **inactivity** alerts them of that reason."
            if is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR])
            else "Are you sure you want to close the ticket?"
        )
        await interaction.response.send_message(content=message, ephemeral=True, view=options(interaction.client))


class LockBtn(discord.ui.Button):
    def __init__(self, label: str = "🔒 Lock Ticket"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:LockBtn",
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]):
            await interaction.response.send_message(
                content="Only staff members can use this button.",
                ephemeral=True
            )
            return

        ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)
        await interaction.client.ticket_manager.toggle_ticket_lock(ticket)
        self.label = "🔓 Unlock Ticket" if ticket.locked else "🔒 Lock Ticket"
        from extensions.ticketsystem.views.containers.close import CloseContainer
        upd_view = CloseContainer.for_category(ticket.category, locked=ticket.locked)
        await interaction.response.edit_message(view=upd_view)


class RenameRunBtn(discord.ui.Button):
    def __init__(self, label: str = "Run Rename"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:RenameRunBtn",
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles=[Roles.ADMIN]):
            await interaction.response.send_message("Only Administrators can use this button.", ephemeral=True)
            return

        ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)
        if not ticket.rename_data:
            await interaction.response.send_message("Could not fetch names for rename.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await process_rename(
            interaction.client,
            interaction,
            ticket.rename_data.old_profile.name,
            ticket.rename_data.new_profile.name
        )


class RenamePrintCMD(discord.ui.Button):
    def __init__(self, label: str = "Print Rename CMD"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:RenamePrintCMD",
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles=[Roles.ADMIN]):
            await interaction.response.send_message("Only Administrators can use this button.", ephemeral=True)
            return

        ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)
        if not ticket.rename_data:
            await interaction.response.send_message("Could not fetch names for rename.", ephemeral=True)
            return

        old = ticket.rename_data.old_profile.name
        new = ticket.rename_data.new_profile.name
        await interaction.response.send_message(
            f"```sh\nservers/scripts/player-rename.sh \"{old}\" \"{new}\" \"{interaction.user.name}\" "
            f"| mysql -u {config['DATABASE']['MARIADB_USER']} -p'{config['DATABASE']['MARIADB_PASSWORD']}' teeworlds\n```",
            ephemeral=True
        )


class BanAppealFindBanBtn(discord.ui.Button):
    def __init__(self, label: str = "Find Ban"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:BanAppealFindBanBtn",
        )
        self._ban_cache: dict[str, list[discord.Message]] = {}

    @staticmethod
    async def from_sqlite_database():
        bans_list = []
        conn = sqlite3.connect("data/ticket-system/db.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT ip, name, expires, reason, moderator FROM bans")
        for ip, name, expires, reason, moderator in cursor.fetchall():
            expires_dt = datetime.fromisoformat(expires) if isinstance(expires, str) else expires
            if expires_dt and expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            bans_list.append({"ip": ip, "name": name, "expires": expires_dt, "reason": reason, "moderator": moderator})
        conn.close()
        return bans_list

    async def search_discord_history(self, interaction, address: str):
        if address in self._ban_cache:
            return self._ban_cache[address]
        results = []
        ban_channel = interaction.client.get_channel(Channels.BANS)
        if ban_channel:
            async for msg in ban_channel.history(limit=1000, oldest_first=False):
                match = re.search(BAN_RE, msg.content)
                if match and ip_matches(address, match["ip_range"]):
                    results.append(msg)
        self._ban_cache[address] = results
        return results

    async def format_ban_messages_embed(self, messages, address):
        now = datetime.now(timezone.utc)
        grouped_bans = {}

        for message in messages:
            regex = re.search(BAN_RE, message.content)
            if not regex:
                continue

            try:
                dt = datetime.strptime(regex['timestamp'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                ban_duration_td = to_discord_timestamp(dt, style='R')
            except ValueError:
                ban_duration_td = None

            expiry_info = (
                "**Expired**") if ban_duration_td and now > dt else f"**Expires:** {ban_duration_td}" if ban_duration_td else "ERROR"  # noqa
            name = strip_surrounding_quotes(regex['banned_user'] or '').strip() or "Unknown"
            reason = regex['reason']
            author = regex['author']
            url = message.jump_url
            ip_addr = regex['ip_range']
            is_range = "-" in ip_addr
            ip_display = f"> :exclamation: **Range Ban:** `{ip_addr}`\n" if is_range else ""
            entry = f"{ip_display}> **Reason:** {reason}\n> **By:** {author}\n> {expiry_info}\n🔗 [Jump to Message]({url})"
            grouped_bans.setdefault(name, []).append(entry)

        db_bans = await self.from_sqlite_database()

        for ban in db_bans:
            if not ip_matches(address, ban['ip']):
                continue
            expiry_info = "**Expired**" if ban['expires'] and now > ban[
                'expires'] else f"**Expires:** {to_discord_timestamp(ban['expires'], style='R')}" if ban[
                'expires'] else "ERROR"
            is_range = "-" in ban['ip']
            ip_display = f"> :exclamation: **Range Ban:** `{ban['ip']}`\n" if is_range else ""
            entry = f"{ip_display}> **Reason:** {ban['reason']}\n> **By:** {ban['moderator']}\n> {expiry_info}"
            grouped_bans.setdefault(ban['name'], []).append(entry)

        total_bans = sum(len(entries) for entries in grouped_bans.values())

        embed = discord.Embed(
            title=f"{'One ban' if total_bans == 1 else f'{total_bans} bans'} found for IP `{address}`",
            color=discord.Color.red()
        )

        if total_bans == 0:
            embed.description = "Could not parse any valid ban messages or database bans."
            return embed

        for name, entries in grouped_bans.items():
            embed.add_field(name=f"NAME: {name}", value="\n\n".join(entries)[:1024], inline=False)

        return embed

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]):
            await interaction.response.send_message("Only staff can use this button.", ephemeral=True)
            return

        ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)
        if not ticket.appeal_data or not ticket.appeal_data.address:
            await interaction.response.send_message("No address found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        messages = await self.search_discord_history(interaction, ticket.appeal_data.address)
        embed = await self.format_ban_messages_embed(messages, ticket.appeal_data.address)
        await interaction.edit_original_response(embed=embed)


class ReportClaimBtn(discord.ui.Button):
    def __init__(self, label: str = "Claim"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,  # noqa
            custom_id="Ticket:ReportClaimBtn",
        )
        self.scores = {}
        self.lock = asyncio.Lock()
        self.click_count = 0

    async def callback(self, interaction: discord.Interaction):
        if is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]):
            ticket = await interaction.client.ticket_manager.get_ticket(interaction.channel)

            if ticket.creator == interaction.user:
                await interaction.response.send_message("You can't claim your own ticket!", ephemeral=True)
                return

            if ticket.state == TicketState.CLAIMED:
                await interaction.response.send_message("This ticket has already been claimed.", ephemeral=True)
                return

            async with self.lock:
                await ticket.set_state(state=TicketState.CLAIMED)
                button.disabled = True
                button.label = "Claimed"
                await interaction.response.edit_message(view=self.view)

                log.info(f"{interaction.user} (ID: {interaction.user.id}) claimed ticket {interaction.channel.name}.")

                score_file = "data/ticket-system/scores.json"

                try:
                    with open(score_file, "r", encoding="utf-8") as file:
                        self.scores = json.load(file)
                except FileNotFoundError:
                    self.scores = {}

                user_id = str(interaction.user.id)
                self.scores[user_id] = self.scores.get(user_id, 0) + 1
                with open(score_file, "w", encoding="utf-8") as file:
                    json.dump(self.scores, file)

            await interaction.response.send_message(
                f"{interaction.user.mention}, thanks for taking care of this! Score +1.", ephemeral=True
            )
            await interaction.channel.send(
                f"{interaction.user.mention} is on their way to help you.",
                allowed_mentions=discord.AllowedMentions(users=False)
            )
        else:
            responses = {
                1: "This button is for moderators only!",
                2: "Stop clicking me!",
                3: "I'll close your ticket if you keep going!",
                4: ":triumph: You did not just do that!",
                5: "(╯°□°)╯︵ ┻━┻",
                6: "┬─┬ノ( º _ ºノ)"
            }
            self.click_count += 1
            if self.click_count in responses:
                await interaction.response.send_message(responses[self.click_count], ephemeral=True)
            if self.click_count == 6:
                self.click_count = 4
