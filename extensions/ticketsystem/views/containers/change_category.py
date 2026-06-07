import discord

from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator


class ChangeCategoryContainer(discord.ui.LayoutView):
    """
    Shown when a ticket is being switched to a category that needs more info.
    Subclasses set ``title``, ``intro``, ``submit_custom_id`` and implement ``make_modal``.
    """

    title: str = ""
    intro: str = ""
    submit_custom_id: str = ""

    def __init__(self, ticket):
        super().__init__(timeout=None)
        self.ticket = ticket
        self.message: discord.Message | None = None

        btn = discord.ui.Button(
            label="📥 Submit",
            style=discord.ButtonStyle.secondary,  # noqa
            custom_id=self.submit_custom_id,
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(self.title),
                large_seperator(),
                discord.ui.TextDisplay(self.intro),
                large_seperator(),
                discord.ui.TextDisplay("-# This ticket has been locked for now."),
                discord.ui.ActionRow(btn),
                accent_colour=TICKET_ACCENT,
            )
        )
        btn.callback = self.submit

    def make_modal(self, interaction: discord.Interaction) -> discord.ui.Modal:
        raise NotImplementedError

    async def submit(self, interaction: discord.Interaction):
        modal = self.make_modal(interaction)
        modal.origin_message = self.message
        await interaction.response.send_modal(modal)
