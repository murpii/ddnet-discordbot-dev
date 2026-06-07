import contextlib
import logging

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.utils import utcnow

from utils.containers import GuideView, NoticeView, avatar_file
from . import rtfm
from .render import render_guide
from .store import DEFAULT_LANG, get_guide, load_guides, normalize_lang

log = logging.getLogger()


class HelperCommands(commands.Cog, name="Help Commands"):
    __doc__ = "Commands related to help, settings, and lookup utilities."

    def __init__(self, bot):
        self.bot = bot
        self.commands = []
        self.tables = rtfm.load_tables()
        # names of the prefix commands generated from data/config/guides.json, so we
        # can remove them again on reload.
        self.generated: list[str] = []

    async def send_view(self, ctx: commands.Context, view: discord.ui.LayoutView, files: list | None = None):
        kwargs = {"view": view}
        if files:
            kwargs["files"] = files
        with contextlib.suppress(discord.Forbidden):
            if ctx.interaction:
                await ctx.interaction.followup.send(**kwargs)
            else:
                await self.bot.reply(message=ctx.message, **kwargs)

    async def build_guide(self, ctx: commands.Context, text: str, *, style: str = "guide"):
        if style == "notice":
            await self.send_view(ctx, NoticeView(text))
        else:
            await self.send_view(ctx, GuideView(text), [avatar_file()])

    def make_guide_command(self, name: str, aliases: list) -> commands.Command:
        async def callback(ctx: commands.Context, lang: str = None):
            chosen = normalize_lang(lang) if lang else DEFAULT_LANG
            result = render_guide(name, chosen)
            if result is None:
                return
            view, files = result
            await self.send_view(ctx, view, files)

        callback.__name__ = f"guide_{name}"
        return commands.Command(callback, name=name, aliases=list(aliases))

    def register_guide(self, name: str) -> bool:
        guide = get_guide(name)
        if guide is None:
            return False
        cmd = self.make_guide_command(name, guide.get("aliases", []))
        try:
            self.bot.add_command(cmd)
        except commands.CommandRegistrationError as error:
            log.warning("Guides: could not register %r: %s", name, error)
            return False
        # listed under this cog in /help (get_commands() reads __cog_commands__),
        # without setting cmd.cog (which would break invoke).
        self.__cog_commands__ = (*self.__cog_commands__, cmd)
        self.generated.append(name)
        return True

    def unregister_guide(self, name: str) -> None:
        cmd = self.bot.remove_command(name)
        if cmd is not None:
            self.__cog_commands__ = tuple(c for c in self.__cog_commands__ if c is not cmd)
        if name in self.generated:
            self.generated.remove(name)

    def register_all_guides(self) -> None:
        for name in load_guides():
            self.register_guide(name)

    async def rtfm_autocomplete(self, _: discord.Interaction, name: str) -> list[Choice[str | int | float]]:
        setting_names = self.commands
        filtered_settings = [
            setting for setting in setting_names if name.lower() in setting.lower()
        ]
        return [
            app_commands.Choice(name=setting, value=setting)
            for setting in filtered_settings[:20]
        ]

    @commands.Cog.listener()
    async def on_ready(self):
        self.commands = rtfm.get_setting_names(self.tables)

    @commands.hybrid_command(
        name="rtfm",
        with_app_command=True,
        description="Displays a server or client setting along with its description")
    @app_commands.autocomplete(setting=rtfm_autocomplete)
    @app_commands.describe(setting="The setting you're looking for")
    async def rtfm(self, ctx: commands.Context, setting: str):
        await ctx.defer(ephemeral=bool(ctx.interaction))
        result = rtfm.get_setting_description(self.tables, setting)
        if not result:
            await ctx.send("Setting not found.")
            return

        rtfm.floats_to_int(result)
        resp = "".join(
            f"```ansi\n\x1b[34m{key}\x1b[38m: {value}```"
            for key, value in result.items()
            if not isinstance(value, float) and value != '""'
        )
        await self.build_guide(ctx, (
            f"## {setting}\n"
            f"{resp}\n"
            f"**URL:** {rtfm.URL}"
        ))

    @commands.command(aliases=["kog", "login", "registration"])
    async def kog_login(self, ctx: commands.Context):
        title = "KoG affiliation" if ctx.invoked_with == "kog" else "KoG Account Registration and Migration"
        text = (
            f"## {title}\n"
            "First and foremost: DDNet and KoG aren't affiliated.\n\n"
            "If you need help on a server related to KoG, "
            "join their Discord server by clicking on the link below.\n\n"
            "**URL:** https://discord.kog.tw/"
        )
        if ctx.invoked_with in ["login", "registration"]:
            text += (
                "\n\n**Registration process:**\n"
                "https://discord.com/channels/342003344476471296/941355528242749440/1129043200527569018\n"
                "**Migration process:**\n"
                "https://discord.com/channels/342003344476471296/941355528242749440/1129043332211945492\n"
                "**How to login on KoG servers:**\n"
                "https://discord.com/channels/342003344476471296/941355528242749440/1129043447517564978\n"
                "**Video Guide:**\n"
                "https://www.youtube.com/watch?v=d1kbt-srlac"
            )
        text += "\n-# You are not required to log-in on a DDNet server."
        await self.build_guide(ctx, text)

    @commands.command(aliases=["utc", "utc-time", "utc-now"])
    async def utc_now(self, ctx: commands.Context):
        await self.build_guide(
            ctx,
            f"Current UTC Time: `{utcnow().strftime('%YY-%mM-%dD %HH:%MM')}`",
            style="notice",
        )
