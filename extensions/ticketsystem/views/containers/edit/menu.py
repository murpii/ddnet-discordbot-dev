import discord

from extensions.ticketsystem import actions
from extensions.ticketsystem.ticket import Ticket, TicketCategory
from extensions.ticketsystem.utils import fetch_rank_from_demo, format_finishes
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.checks import is_staff

CATEGORY_CHOICES = [
    ("Report", TicketCategory.REPORT),
    ("Rename", TicketCategory.RENAME),
    ("Ban Appeal", TicketCategory.BAN_APPEAL),
    ("VPN Ban Appeal", TicketCategory.VPN_BAN_APPEAL),
    ("Complaint", TicketCategory.COMPLAINT),
    ("Admin-Mail", TicketCategory.ADMIN_MAIL),
    ("Community Application", TicketCategory.COMMUNITY_APP),
]
CATEGORY_LABELS = {cat: label for label, cat in CATEGORY_CHOICES}


class CategorySelect(discord.ui.Select):
    def __init__(self, ticket: Ticket):
        self.ticket = ticket
        options = [
            discord.SelectOption(label=label, value=cat.value, default=(cat == ticket.category))
            for label, cat in CATEGORY_CHOICES
        ]
        super().__init__(placeholder="Change category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles="mods"):
            await interaction.response.send_message("Only staff can use this.", ephemeral=True)
            return

        category_enum = TicketCategory(self.values[0])
        if category_enum == self.ticket.category:
            label = CATEGORY_LABELS.get(category_enum, category_enum.value)
            await interaction.response.send_message(
                f"This ticket is already a **{label}** ticket.", ephemeral=True
            )
            return

        await actions.apply_category_change(
            interaction, interaction.client.ticket_manager, self.ticket, category_enum
        )


class InviteSelect(discord.ui.MentionableSelect):
    def __init__(self):
        super().__init__(placeholder="Invite a user or role", min_values=1, max_values=5)

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles="mods"):
            await interaction.response.send_message("Only staff can use this.", ephemeral=True)
            return

        lines = []
        for entity in self.values:
            if isinstance(entity, discord.Role) and entity.id == interaction.guild.default_role.id:
                lines.append("Inviting the default role is prohibited.")
                continue
            lines.append(await actions.invite_entity(interaction.channel, entity))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class RenameChannelModal(discord.ui.Modal, title="Rename ticket channel"):
    new_name = discord.ui.TextInput(
        label="New channel name",
        max_length=100,
        placeholder="e.g. report-spammer",
    )

    def __init__(self, ticket: Ticket):
        super().__init__(timeout=300)
        self.ticket = ticket

    async def on_submit(self, interaction: discord.Interaction):
        status = await actions.rename_ticket_channel(self.ticket, self.new_name.value)
        await interaction.response.send_message(status, ephemeral=True)


class RenameChannelButton(discord.ui.Button):
    def __init__(self, ticket: Ticket):
        super().__init__(label="Rename channel", style=discord.ButtonStyle.secondary)  # noqa
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RenameChannelModal(self.ticket))


class RescanDemosButton(discord.ui.Button):
    # temporary, remove once old rename tickets are checked
    def __init__(self, ticket: Ticket):
        super().__init__(label="Rescan demos", style=discord.ButtonStyle.secondary)  # noqa
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction.user, roles="mods"):
            await interaction.response.send_message("Only staff can use this.", ephemeral=True)
            return
        if not self.ticket.rename_data:
            await interaction.response.send_message("Could not fetch names for rename.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        bot = interaction.client
        session = await bot.session_manager.get_session("TicketListeners")
        names = (
            self.ticket.rename_data.old_profile.name,
            self.ticket.rename_data.new_profile.name,
        )

        finishes = []
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            if any(attachment.filename.endswith(".demo") for attachment in message.attachments):
                finishes.extend(await fetch_rank_from_demo(bot, message, session, names))

        if not finishes:
            await interaction.followup.send("No finishes for the old or new name found in demos.", ephemeral=True)
            return

        for text in format_finishes(finishes):
            await interaction.channel.send(text)
        await interaction.followup.send(f"Found {len(finishes)} finish(es).", ephemeral=True)


class TicketEditView(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=300)
        self.ticket = ticket
        buttons = [RenameChannelButton(ticket)]
        if ticket.category == TicketCategory.RENAME:
            buttons.append(RescanDemosButton(ticket))
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## 🛠️ Edit ticket\n"
                    "Change the category, invite a user or role, or rename the channel.\n"
                    "-# All ticket data is kept in the channel topic, so renaming is safe."
                ),
                large_seperator(),
                discord.ui.ActionRow(CategorySelect(ticket)),
                discord.ui.ActionRow(InviteSelect()),
                discord.ui.ActionRow(*buttons),
                accent_colour=TICKET_ACCENT,
            )
        )
