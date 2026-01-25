import json
import logging
from typing import Union, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.checks import check_dm_channel, is_staff
from . import embeds
from .ticket import TicketCategory
from .views import buttons
from .views.buttons import (
    ReportButton, ComplaintButton, AdminMailButton,
    RenameButton, BanAppealButton, CommunityAppButton
)
from .views.confirm import ConfirmView
from .views.containers.MainMenu import MainMenuContainer
from .views.containers.admin_mail import AdminMailContainer
from .views.containers.community_app import CommunityAppContainer
from .views.containers.complaint import ComplaintContainer
from .views.containers.report import ReportContainer
from .views.modals import ban_appeal_m
from .transcript import TicketTranscript
from extensions.ticketsystem.views.subscribe import SubscribeMenu
from extensions.ticketsystem.utils import fetch_rank_from_demo
from constants import Guilds, Channels, Roles

log = logging.getLogger("tickets")


def predicate(interaction: discord.Interaction) -> bool:
    return interaction.channel.id in interaction.client.ticket_manager.tickets


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.update_scores_topic.start()
        self.mentions = set()
        self.message_cache = {}
        self.ticket_manager = bot.ticket_manager

    async def cog_load(self):
        session = await self.bot.session_manager.get_session(self.__class__.__name__)
        self.session = buttons.BanAppealButton.session = ban_appeal_m.BanAppealModal.session = session

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    async def transcript(
            self,
            ticket,
            interaction: Optional[discord.Interaction] = None,
            postscript: Optional[str] = None,
    ):
        """
        Creates a transcript for the specified ticket and notifies the ticket creator.

        Args:
            ticket: The ticket object for which the transcript is created.
            interaction (Optional[discord.Interaction]): The interaction associated with the request, if any.
            postscript (Optional[str]): The message sent to the ticket author.
            inactive (bool): True/False if the ticket is closed due to inactivity.
        """
        transcript = TicketTranscript(self.bot, ticket)
        await transcript.create_transcript(interaction)
        await transcript.notify_ticket_creator(interaction, postscript)
        transcript.cleanup()

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="ticket_menu", description="The ticket system menu with all buttons")
    async def ticket_menu(self, interaction: discord.Interaction):
        """|coro|
        Displays the ticket system menu with various options for users.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
        """
        await interaction.channel.send(
            view=MainMenuContainer(self.bot)
        )
        await interaction.response.send_message(content="Done!", ephemeral=True)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="sub_menu", description="Internal ticket subscription menu")
    async def subscribe_menu(self, interaction: discord.Interaction):
        """|coro|
        Displays the ticket subscription menu for managing notifications.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        await interaction.followup.send(
            "Choose the ticket categories you wish to receive notifications for, "
            "or use the Subscribe/Unsubscribe buttons to manage notifications for all categories.",
            view=SubscribeMenu(self.bot),
        )

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.check(predicate)
    @app_commands.command(name="invite", description="Adds a user or role to the ticket")
    @app_commands.describe(user="@mention the user OR role to invite")
    async def invite(self, interaction: discord.Interaction, user: Union[discord.Member, discord.Role]):
        """|coro|
        Invites a specified user or role to a ticket channel.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
            user (Union[discord.Member, discord.Role]): The user or role to be invited to the ticket channel.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        # technically not required
        if not is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]):
            await interaction.followup.send("Only moderators are allowed to invite.")
            return
        if (
                isinstance(user, discord.Role)
                and user.id == interaction.guild.default_role.id
        ):
            await interaction.followup.send("Inviting the default role is prohibited.")
            return
        if isinstance(user, discord.Member):
            await interaction.channel.set_permissions(
                user, view_channel=True, send_messages=True
            )
            await interaction.followup.send(
                f"{user.mention} has been added to the channel."
            )
        if isinstance(user, discord.Role):
            await interaction.channel.set_permissions(
                user, view_channel=True, send_messages=True
            )
            await interaction.followup.send(
                f"{user.mention} role has been added to the channel."
            )

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="close", description="Closes a ticket.")
    @app_commands.describe(message="The message intended for the recipient to receive.")
    async def close(self, interaction: discord.Interaction, message: str = None):
        """|coro|
        Closes a ticket and sends a message to the recipient.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
            message (str, optional): A message to be sent to the ticket recipient upon closure.
        """
        ticket = await self.ticket_manager.get_ticket(interaction.channel)

        if (
                not is_staff(interaction.user, roles=[
                    Roles.ADMIN,
                    Roles.DISCORD_MODERATOR,
                    Roles.MODERATOR
                ])
                and interaction.user != ticket.creator
        ):
            await interaction.response.send_message(  # noqa
                content="This ticket does not belong to you.",
                ephemeral=True
            )
            return

        if ticket.being_closed:
            await interaction.response.send_message(  # noqa
                content="Ticket is already being closed.",
                ephemeral=True
            )
            return

        if ticket is None:
            return

        async with ticket.lock:
            ticket.being_closed = True
            try:
                if message:
                    if not await check_dm_channel(ticket.creator):
                        await interaction.response.send_message(
                            content="The ticket author **cannot** be DMed, "
                                    "meaning they wont receive your message. Continue?",
                            ephemeral=True,
                            view=ConfirmView(self.bot, closing=True, message=message)
                        )
                        return
                    await ticket.channel.send(message)

                await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
                await self.transcript(ticket, interaction, message)
                await self.ticket_manager.del_ticket(ticket=ticket)

                log.info(
                    f"{interaction.user} [ID: {interaction.user.id}] "
                    f"closed a {ticket.category.value.title()} ticket made by {ticket.creator} [ID: {ticket.creator.id}]. "
                    f"Removed channel named {interaction.channel.name} [ID: {interaction.channel_id}]"
                )

                if interaction.response.is_done():  # noqa
                    await interaction.channel.delete()
                    if len(interaction.channel.category.channels) == 0:
                        await interaction.channel.category.delete()

            except Exception as e:
                log.exception(f"{ticket.channel.name}: Error during ticket closure:\n{e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        content=f"An error occurred while closing the ticket:\n{e}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(f"An error occurred while closing the ticket: {e}", ephemeral=True)
            finally:
                ticket.being_closed = False

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="change_category", description="Changes a ticket's category.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Report", value=TicketCategory.REPORT.value),
        app_commands.Choice(name="Rename", value=TicketCategory.RENAME.value),
        app_commands.Choice(name="Ban Appeal", value=TicketCategory.BAN_APPEAL.value),
        app_commands.Choice(name="Complaint", value=TicketCategory.COMPLAINT.value),
        app_commands.Choice(name="Admin-Mail", value=TicketCategory.ADMIN_MAIL.value),
        app_commands.Choice(name="Community Application", value=TicketCategory.COMMUNITY_APP.value),
    ])
    async def change_category(
            self,
            interaction: discord.Interaction,
            category: app_commands.Choice[str]
    ):
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        if not ticket:
            await interaction.response.send_message(
                "This is not a ticket channel.",
                ephemeral=True,
            )
            return

        category_enum = TicketCategory(category.value)

        if ticket.category == category_enum:
            await interaction.response.send_message(
                f"This ticket is already a **{category.name}** ticket.",
                ephemeral=True,
            )
            return

        # Special-case categories that need validation or start flows
        if category_enum == TicketCategory.RENAME:
            content = (
                "..."
            )
            view = discord.ui.View()
            view.add_item(RenameButton(self.bot, label="Submit", ticket=ticket))
            await interaction.response.send_message(content=content, view=view)
            if not ticket.locked:
                await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False)
            return

        if category_enum == TicketCategory.BAN_APPEAL:
            content = (
                "In order to appeal a ban, we need a couple of infos first. "
                "Click the submit button to start the process."
            )
            view = discord.ui.View()
            view.add_item(BanAppealButton(self.bot, label="Submit", ticket=ticket))
            await interaction.response.send_message(content=content, view=view)
            if not ticket.locked:
                await self.ticket_manager.toggle_ticket_lock(ticket=ticket, send_msg=False)
            return

        await self.ticket_manager.update_ticket(
            interaction,
            ticket=ticket,
            category=category_enum,
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.TextChannel, after: discord.TextChannel):
        if after.guild.id != Guilds.DDNET:
            return

        before_cat = before.category.name if before.category else None
        after_cat = after.category.name if after.category else None

        before_c = before_cat and before_cat.startswith("Tickets")
        after_c = after_cat and after_cat.startswith("Tickets")

        if before.id not in self.ticket_manager.tickets and not after_c:
            return

        if before.id in self.ticket_manager.tickets and not after_c:
            await self.ticket_manager.del_ticket(after)
            log.info(
                f"Ticket Channel '{after.name}' has been detached from '{before_cat or 'No category'}' "
                f"to '{after_cat or 'No category'}' and is no longer considered as a ticket."
            )
        elif not before_c:
            try:
                await self.ticket_manager.create_ticket(after)
                log.info(
                    f"Ticket Channel '{after.name}' has been moved from '{before_cat or 'No category'}' "
                    f"to '{after_cat or 'No category'}' and is now considered as a ticket."
                )
            except ValueError as e:
                log.error(e)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="cleanup", description="Removes tickets from DB which no longer exist.")
    async def cleanup_database(self, interaction: discord.Interaction):
        """|coro|
        Cleans up the database by removing tickets that no longer exist.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
        """
        query = """
                SELECT channel_id
                FROM discordbot_tickets \
                """
        rows = await self.bot.fetch(query, fetchall=True)
        deleted_tickets = []

        for row in rows:
            channel_id = row[0]
            if int(channel_id) not in self.ticket_manager.tickets:
                delete_query = """
                               DELETE
                               FROM discordbot_tickets
                               WHERE channel_id = %s \
                               """
                await self.bot.upsert(delete_query, channel_id)
                deleted_tickets.append(f"Channel ID: {channel_id}")

        if deleted_tickets:
            message = "Deleted tickets:\n" + "\n".join(deleted_tickets)
            await interaction.response.send_message(message, ephemeral=True)  # noqa
        else:
            await interaction.response.send_message("No tickets were deleted.", ephemeral=True)  # noqa

    @invite.error
    @close.error
    @change_category.error
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.CheckFailure):
        if isinstance(error, app_commands.CheckFailure):
            msg = "This application command can only be used in tickets."
            if interaction.response.is_done():  # noqa
                await interaction.followup.send(content=msg)
            else:
                await interaction.response.send_message(content=msg, ephemeral=True)  # noqa
            interaction.extras["error_handled"] = True

    @tasks.loop(hours=1)
    async def update_scores_topic(self):
        """|asyncio.task|
        Updates the topic of the moderator channel with the top scores.
        """
        score_file = "data/ticket-system/scores.json"
        with open(score_file, "r", encoding="utf-8") as file:
            scores = json.load(file)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        topic = "Issues Resolved:"
        for user_id, score in sorted_scores[:30]:
            topic += f" <@{user_id}> = {score} |"

        topic = topic.rstrip("|")

        if channel := self.bot.get_channel(Channels.MODERATOR):
            await channel.edit(topic=topic)

    @update_scores_topic.before_loop
    async def before_update_scores_topic(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.ticket_manager.load_tickets()

    @commands.Cog.listener("on_message")
    async def del_system_pin_message(self, message: discord.Message):
        if (
                isinstance(message.channel, discord.TextChannel)
                and (
                message.guild.id == Guilds.DDNET
                and message.channel.category.name == "Tickets"
                and message.type is discord.MessageType.pins_add
        )
        ):
            await message.delete()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != Guilds.DDNET:
            return

        try:
            entry = await anext(
                channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete), None
            )
            if not entry or entry.user.bot:
                return
            ticket = self.ticket_manager.tickets[channel.id]
        except discord.Forbidden:
            log.warning("Missing permissions to read audit logs.")
            return
        except KeyError:
            return

        await self.ticket_manager.del_ticket(channel=channel, ticket=ticket)
        log.info(
            "Ticket channel named %s was manually removed by %s.",
            channel.name, entry.user
        )

    @commands.Cog.listener('on_message')
    async def fetch_demo_rank(self, message: discord.Message):
        if (
                not isinstance(message.channel, discord.TextChannel)
                or not message.guild
                or message.guild.id != Guilds.DDNET
                or not message.channel.category
                or message.channel.category.name != "Tickets"
                or not message.attachments
        ):
            return

        ranks = await fetch_rank_from_demo(self.bot, message, self.session)
        if ranks:
            response = "✅ Found record for:\n" + "\n".join(
                f"- `{demo}` (Timestamp: `{timestamp}`)" for demo, timestamp in ranks
            )
            await message.channel.send(response)
