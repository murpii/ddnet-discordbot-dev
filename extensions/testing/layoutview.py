from discord import SeparatorSpacing
from discord.ext import commands
import discord
import random


class TestModal(discord.ui.Modal, title="abc"):
    name = discord.ui.TextInput(
        label="Your name",
        placeholder="Enter name here"
    )

    def __init__(self):
        super().__init__()

        # fixed options for the Select dropdown
        self.select = discord.ui.Select(
            placeholder="Choose your fruit",
            options=[
                discord.SelectOption(label="Apple"),
                discord.SelectOption(label="Banana"),
                discord.SelectOption(label="Cherry")
            ]
        )

        self.add_item(self.select)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Hello {self.name.value}! You picked: {self.select.values}",
            ephemeral=True
        )


class LayoutView(discord.ui.LayoutView):
    action_row = discord.ui.ActionRow()

    @action_row.button(label="Click Me!", style=discord.ButtonStyle.primary)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Hello! You clicked the button.", ephemeral=True)

    container_top = discord.ui.Container(
        discord.ui.TextDisplay("This is the **top section**."),
        accent_colour=discord.Colour.green()
    )


class LayoutExampleView(LayoutView):
    # noinspection PyTypeChecker
    def __init__(self):
        super().__init__()

        btn1 = discord.ui.Button(label="Click me", style=discord.ButtonStyle.secondary)
        btn2 = discord.ui.Button(label="Or me", style=discord.ButtonStyle.success)
        btn3 = discord.ui.Button(label="modal", style=discord.ButtonStyle.red)

        container = discord.ui.Container(
            discord.ui.TextDisplay("This container has an accent color!"),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem("https://i.imgur.com/MSZF3ly.png"),
                discord.MediaGalleryItem("https://i.imgur.com/LWQESh4.mp4"),
                discord.MediaGalleryItem("https://i.imgur.com/dTXraG9.jpeg"),
            ),
            discord.ui.TextDisplay("Some text between!"),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem("https://i.imgur.com/MSZF3ly.png"),
                discord.MediaGalleryItem("https://i.imgur.com/LWQESh4.mp4"),
            ),
            discord.ui.ActionRow(btn1, btn2, btn3),  # <- btn3 instead of modal here
            accent_colour=discord.Colour.orange(),
        )

        self.add_item(container)
        btn1.callback = self._btn1_clicked
        btn2.callback = self._btn2_clicked
        btn3.callback = self._btn3_clicked  # wire the callback

    async def _btn1_clicked(self, interaction: discord.Interaction):
        await interaction.response.send_message("You clicked **Click me**!", ephemeral=True)

    async def _btn2_clicked(self, interaction: discord.Interaction):
        await interaction.response.send_message("You clicked **Or me**!", ephemeral=True)

    async def _btn3_clicked(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TestModal())

    # action_row = discord.ui.ActionRow()
    # @action_row.button(label="Click Me!", style=discord.ButtonStyle.primary)
    # async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     await interaction.response.send_message("Hello! You clicked the button.", ephemeral=True)


class Layout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def layout(self, ctx: commands.Context):
        await ctx.send(view=LayoutExampleView())


async def setup(bot):
    await bot.add_cog(Layout(bot))
