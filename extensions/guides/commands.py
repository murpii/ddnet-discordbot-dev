import logging

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.utils import utcnow

from constants import URLs
from utils.containers import GuideView, NoticeView, avatar_file
from . import rtfm
from .render import render_guide
from .store import LANGUAGES, load_guides, normalize_lang

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()


def guide_names() -> dict:
    names = {}
    for name, guide in load_guides().items():
        names[name] = name
        for alias in guide.get("aliases", []):
            names[alias.lower()] = name
    return names


def language_choices() -> list:
    return [Choice(name=lang, value=lang) for lang in LANGUAGES]


class HelperCommands(commands.Cog, name="Help Commands"):
    __doc__ = "Commands related to help, settings, and lookup utilities."

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.settings = []
        self.tables = rtfm.load_tables()

    async def send_view(self, interaction: discord.Interaction, view: discord.ui.LayoutView, files: list | None = None):
        kwargs = {"view": view}
        if files:
            kwargs["files"] = files
        await interaction.followup.send(**kwargs)

    async def build_guide(self, interaction: discord.Interaction, text: str, *, style: str = "guide"):
        if style == "notice":
            await self.send_view(interaction, NoticeView(text))
        else:
            await self.send_view(interaction, GuideView(text), [avatar_file()])

    async def guide_autocomplete(self, _: discord.Interaction, current: str) -> list[Choice[str]]:
        current = current.lower()
        matched = []
        for token, name in guide_names().items():
            if current in token and name not in matched:
                matched.append(name)
        return [Choice(name=name, value=name) for name in matched[:25]]

    async def rtfm_autocomplete(self, _: discord.Interaction, current: str) -> list[Choice[str]]:
        filtered = [setting for setting in self.settings if current.lower() in setting.lower()]
        return [Choice(name=setting, value=setting) for setting in filtered[:20]]

    @commands.Cog.listener()
    async def on_ready(self):
        self.settings = rtfm.get_setting_names(self.tables)

    @app_commands.command(name="guide", description="Show one of the DDNet help guides")
    @app_commands.describe(
        name="Which guide to show",
        language="Show it in this language, defaults to your Discord language")
    @app_commands.autocomplete(name=guide_autocomplete)
    @app_commands.choices(language=language_choices())
    async def guide(self, interaction: discord.Interaction, name: str, language: str = None):
        await interaction.response.defer()
        chosen = normalize_lang(language or interaction.locale)

        result = render_guide(guide_names().get(name.lower(), name), chosen)
        if result is None:
            await interaction.followup.send(f"There is no guide named `{name}`.", ephemeral=True)
            return

        view, files = result
        await self.send_view(interaction, view, files)

    @app_commands.command(
        name="rtfm",
        description="Displays a server or client setting along with its description")
    @app_commands.autocomplete(setting=rtfm_autocomplete)
    @app_commands.describe(setting="The setting you're looking for")
    async def rtfm(self, interaction: discord.Interaction, setting: str):
        await interaction.response.defer(ephemeral=True)
        result = rtfm.get_setting_description(self.tables, setting)
        if not result:
            await interaction.followup.send("Setting not found.")
            return

        rtfm.floats_to_int(result)
        resp = "".join(
            f"```ansi\n\x1b[34m{key}\x1b[38m: {value}```"
            for key, value in result.items()
            if not isinstance(value, float) and value != '""'
        )
        await self.build_guide(interaction, (
            f"## {setting}\n"
            f"{resp}\n"
            f"**URL:** {URLs.DDNET_SETTINGS_COMMANDS}"
        ))

    @app_commands.command(name="utc", description="Show the current UTC time")
    async def utc(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.build_guide(
            interaction,
            f"Current UTC Time: `{utcnow().strftime('%YY-%mM-%dD %HH:%MM')}`",
            style="notice",
        )
