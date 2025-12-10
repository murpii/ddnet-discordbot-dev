import discord

from extensions.moderator.views.modals.ban import BanModal


class BanButton(discord.ui.Button):
    def __init__(self, bot, member: discord.abc.User):
        super().__init__(label="Ban", style=discord.ButtonStyle.danger)  # noqa
        self.bot = bot
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        modal = BanModal(self.bot, self.member)
        await interaction.response.send_modal(modal)
