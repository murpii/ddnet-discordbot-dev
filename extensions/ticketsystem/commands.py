from typing import Union

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import check_dm_channel, is_staff
from . import actions
from .ticket import TicketCategory
from .views import buttons
from .views.confirm import ConfirmView
from .views.containers.MainMenu import MainMenuContainer
from .views.modals import ban_appeal_m
from constants import Guilds, Roles


def predicate(interaction: discord.Interaction) -> bool:
    return interaction.channel.id in interaction.client.ticket_manager.tickets


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.mentions = set()
        self.message_cache = {}
        self.ticket_manager = bot.ticket_manager

    async def cog_load(self):
        session = await self.bot.session_manager.get_session(self.__class__.__name__)
        self.session = buttons.BanAppealButton.session = ban_appeal_m.BanAppealModal.session = session

    async def cog_unload(self):
        await self.bot.session_manager.close_session(self.__class__.__name__)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="ticket_menu", description="The ticket system menu with all buttons")
    async def ticket_menu(self, interaction: discord.Interaction):
        """|coro|
        Displays the ticket system menu with various options for users.

        Args:
            interaction (discord.Interaction): The interaction object representing the user's action.
        """
        await interaction.channel.send(view=MainMenuContainer(self.bot))
        await interaction.response.send_message(content="Done!", ephemeral=True)

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

        await interaction.followup.send(await actions.invite_entity(interaction.channel, user))

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="close", description="Closes a ticket.")
    @app_commands.describe(message="The message intended for the recipient to receive.")
    async def close(self, interaction: discord.Interaction, message: str = None):
        """|coro|
        Closes a ticket and sends a message to the recipient.
        """
        ticket = await self.ticket_manager.get_ticket(interaction.channel)
        if ticket is None:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)  # noqa
            return

        if (
                not is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR])
                and interaction.user != ticket.creator
        ):
            await interaction.response.send_message("This ticket does not belong to you.", ephemeral=True)  # noqa
            return

        if ticket.being_closed:
            await interaction.response.send_message("Ticket is already being closed.", ephemeral=True)  # noqa
            return

        # Staff-supplied message but the creator can't be DMed: confirm before closing.
        if message and not await check_dm_channel(ticket.creator):
            await interaction.response.send_message(  # noqa
                ephemeral=True,
                view=ConfirmView(
                    self.bot,
                    closing=True,
                    message=message,
                    prompt="The ticket author **cannot** be DMed, "
                           "meaning they wont receive your message. Continue?",
                ),
            )
            return

        await self.ticket_manager.close_ticket(interaction, ticket, message=message)

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.check(predicate)
    @app_commands.command(name="change_category", description="Changes a ticket's category.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Report", value=TicketCategory.REPORT.value),
        app_commands.Choice(name="Rename", value=TicketCategory.RENAME.value),
        app_commands.Choice(name="Ban Appeal", value=TicketCategory.BAN_APPEAL.value),
        app_commands.Choice(name="VPN Ban Appeal", value=TicketCategory.VPN_BAN_APPEAL.value),
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

        await actions.apply_category_change(
            interaction, self.ticket_manager, ticket, category_enum
        )

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
