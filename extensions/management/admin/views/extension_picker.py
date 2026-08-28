import discord
from discord.ext import commands

from bot import extensions

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


class ExtensionSelect(discord.ui.Select):
    def __init__(self, bot: "DDNet", action, extensions, index):
        self.bot = bot
        self.action = action

        options = [
            discord.SelectOption(
                label=ext.split(".")[-1],
                value=ext,
            )
            for ext in extensions
        ]

        super().__init__(
            placeholder=f"Select extension ({index})",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"ext:{action}:{index}",
        )

    async def callback(self, interaction: discord.Interaction):
        extension = self.values[0]

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            if self.action == "load":
                await self.bot.load_extension(extension)
            elif self.action == "unload":
                await self.bot.unload_extension(extension)
            elif self.action == "reload":
                await self.bot.reload_extension(extension)

            await self.bot.tree.sync(guild=interaction.guild)

            await interaction.edit_original_response(
                content=f"{self.action.capitalize()}ed `{extension}` successfully."
            )

        except commands.ExtensionAlreadyLoaded:
            await interaction.edit_original_response(
                content=f"`{extension}` is already loaded."
            )
        except commands.ExtensionNotLoaded:
            await interaction.edit_original_response(
                content=f"`{extension}` is not loaded."
            )
        except commands.ExtensionNotFound:
            await interaction.edit_original_response(
                content=f"`{extension}` not found."
            )
        except commands.ExtensionFailed as e:
            await interaction.edit_original_response(
                content=f"`{extension}` failed: {e}"
            )


class ExtensionSelectView(discord.ui.View):
    def __init__(self, bot: "DDNet", action):
        super().__init__(timeout=120)
        self.bot = bot
        self.action = action

        all_extensions = [cog for cog, _ in extensions]

        for idx, chunk in enumerate(chunked(all_extensions, 25), start=1):
            self.add_item(
                ExtensionSelect(bot, action, chunk, idx)
            )
