from discord import SeparatorSpacing
from discord.ext import commands
import discord
import random

from extensions.ticketsystem.views.containers.rename import RenameContainer


class FruitModal(discord.ui.Modal, title="abc"):
    fruit_select = discord.ui.Label(
        text="Your favorite fruit",
        # setting an optional description
        # this will appear below the label on desktop, and below the component on mobile
        description="Please select your favorite fruit from the list.",
        # this is where a select (or TextInput) component goes
        component=discord.ui.Select(
            placeholder="Select your favorite fruit...",  # this is optional
            # we can make it optional too using the required kwarg
            # defaults to True (required)
            required=True,
            options=[
                discord.SelectOption(label="Apple", value="apple"),
                discord.SelectOption(label="Banana", value="banana"),
                discord.SelectOption(label="Cherry", value="cherry"),
            ]
        )
    )

    # adding a TextInput for the sake of example
    reason = discord.ui.Label(
        text="Why is that your favorite fruit?",
        component=discord.ui.TextInput(
            placeholder="Tell us why...",
            # making this one optional -- we don't really need to know
            required=False
        )
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:

        chosen_fruit = self.fruit_select.component.values[0]
        if reason := self.reason.component.value:
            response = f"Your favorite fruit is {chosen_fruit} because {reason}"
        else:
            response = f"Your favorite fruit is {chosen_fruit} but you didn't tell us why :("

        await interaction.response.send_message(response)


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
            discord.ui.File("attachment://deepfly.txt"),
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
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),
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
        await interaction.response.send_modal(FruitModal())

    # action_row = discord.ui.ActionRow()
    # @action_row.button(label="Click Me!", style=discord.ButtonStyle.primary)
    # async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     await interaction.response.send_message("Hello! You clicked the button.", ephemeral=True)


class Layout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def layout(self, ctx: commands.Context):
        file = discord.File("data/deepfly.txt", filename="deepfly.txt")
        await ctx.send(
            view=LayoutExampleView(),
            file=file
        )


async def setup(bot):
    await bot.add_cog(Layout(bot))

# REFERENCING A DIFFERENT INTERACTION:

# class ExampleModal(discord.ui.Modal):
#     def __init__(self, button: discord.ui.Button):
#         super().__init__(title="Submit Data")
#         self.button = button
#         self.add_item(discord.ui.TextInput(label="Your Input"))
#
#     async def on_submit(self, interaction: discord.Interaction):
#         # Process the modal input here
#         user_input = self.children[0].value
#         await interaction.response.send_message(f"You submitted: {user_input}")
#
#         # Disable the button after the modal is submitted
#         self.button.disabled = True
#         await interaction.message.edit(view=self.button.view)
#
#
# class ExampleView(discord.ui.View):
#     def __init__(self):
#         super().__init__()
#         self.add_item(SubmitButton())
#
#
# class SubmitButton(discord.ui.Button):
#     def __init__(self):
#         super().__init__(label="Submit", style=discord.ButtonStyle.primary)
#
#     async def callback(self, interaction: discord.Interaction):
#         await interaction.response.send_modal(ExampleModal(self))
#
#
# bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
#
#
# @bot.event
# async def on_ready():
#     print(f"Logged in as {bot.user}!")
#
#
# @bot.command()
# async def test(ctx):
#     await ctx.send("Click the button to submit:", view=ExampleView())
