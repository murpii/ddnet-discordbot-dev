from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.containers import INFO_ACCENT, NoticeView

from .render import render_guide
from .store import load_guides, normalize_lang

if TYPE_CHECKING:
    from bot import DDNet


class GuidePickSelect(discord.ui.Select):
    def __init__(self, message: discord.Message):
        self.message = message
        names = sorted(load_guides())[:25]  # discord allows 25 options
        super().__init__(
            placeholder="Pick a guide to reply with",
            options=[discord.SelectOption(label=name) for name in names]
            or [discord.SelectOption(label="(no guides yet)", value="")],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        name = self.values[0]
        result = render_guide(name, normalize_lang(interaction.locale))
        if result is None:
            await interaction.response.edit_message(
                view=NoticeView(f"The `{name}` guide is currently unavailable.")
            )
            return

        view, files = result
        try:
            await self.message.reply(view=view, files=files, mention_author=False)
        except discord.HTTPException:
            await interaction.response.edit_message(
                view=NoticeView("Could not reply to that message. It may have been deleted.")
            )
            return

        await interaction.response.edit_message(
            view=NoticeView(f"Replied with the `{name}` guide.")
        )


class GuidePickView(discord.ui.LayoutView):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=300)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Reply with a guide\n"
                    f"Picking one posts it as a reply to [that message]({message.jump_url})."
                ),
                discord.ui.ActionRow(GuidePickSelect(message)),
                accent_colour=INFO_ACCENT,
            )
        )


class GuideCtxMenu(commands.Cog):
    def __init__(self, bot: "DDNet") -> None:
        self.bot = bot

        self.reply_with_guide = app_commands.ContextMenu(
            name="Reply with a guide",
            callback=self.guide_context,
            type=discord.AppCommandType.message,  # noqa
        )
        self.bot.tree.add_command(self.reply_with_guide)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.reply_with_guide.name,
            type=self.reply_with_guide.type,
        )

    async def guide_context(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_message(view=GuidePickView(message), ephemeral=True)
