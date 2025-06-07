import discord
import contextlib
from discord import app_commands
from discord.ext import commands
import pandas
import numpy as np

from discord.utils import utcnow
from constants import Channels

URL = "https://ddnet.org/settingscommands/"


def floats_to_int(dictionary: dict):
    for key, val in dictionary.items():
        if isinstance(val, float) and not np.isnan(val) and val == int(val):
            dictionary[key] = int(val)
        elif isinstance(val, dict):
            floats_to_int(val)


class HelperCommands(commands.Cog, name="Help Commands"):
    def __init__(self, bot):
        self.bot = bot
        self.commands = []
        self.tables = pandas.read_html(URL)

    def get_setting_names(self) -> list[str]:
        setting_names = []
        for table in self.tables:
            for column in ['Setting', 'Command', 'Tuning']:
                if column in table.columns:
                    setting_names.extend(table[column].dropna().tolist())
        return setting_names

    def get_setting_description(self, setting: str) -> dict | None:
        for table in self.tables:
            table_copy = table.copy()
            table_copy.set_index(table_copy.columns[0], inplace=True)
            if setting in table_copy.index:
                return table_copy.loc[setting].to_dict()
        return None

    async def rtfm_autocomplete(self, _: discord.Interaction, name: str) -> list[app_commands.Choice[str]]:
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
        self.commands = self.get_setting_names()

    @commands.hybrid_command(
        name="rtfm",
        with_app_command=True,
        description="Displays a server or client setting along with its description")
    @app_commands.autocomplete(setting=rtfm_autocomplete)
    @app_commands.describe(setting="The setting you're looking for")
    async def rtfm(self, ctx: commands.Context, setting: str):
        await ctx.defer(ephemeral=bool(ctx.interaction))
        result = self.get_setting_description(setting)
        if not result:
            await ctx.send("Setting not found.")
            return

        resp = ""
        floats_to_int(result)
        for key, value in result.items():
            if not isinstance(value, float) and value != '""':
                resp += f"```ansi\n[34m{key}[38m: {value}```"

        embed = discord.Embed(
            title=setting, description=resp, colour=discord.Colour.blurple()
        )
        embed.add_field(name="URL:", value="https://ddnet.org/settingscommands/")
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            if ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await self.bot.reply(message=ctx.message, embed=embed)

    @commands.command()
    async def staff(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        embed = discord.Embed(
            title="DDNet Staff List",
            description="The link below will give you a full list of all DDNet staff members.",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="URL:", value="https://ddnet.org/staff/")
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command()
    async def configdir(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        url = "https://wiki.ddnet.org/wiki/FAQ#Where_is_the_DDNet_config,_config_directory_or_save_directory?"
        embed = discord.Embed(
            description=f"""
                        ### [DDNet config directory:]({url})
                        __**On Windows:**__
                        Old: `%appdata%\\Teeworlds`
                        New: `%appdata%\\DDNet`
                        __**On Linux:**__
                        Old: `~/.teeworlds`
                        New: `~/.local/share/ddnet`
                        __**On macOS:**__
                        Old: `~/Library/Application Support/Teeworlds`
                        New: `~/Library/Application Support/DDNet`
                        """,
            colour=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command()
    async def deepfly(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        bindconfig = discord.File("data/deepfly.txt", filename="deepfly.txt")
        url = "https://wiki.ddnet.org/wiki/Binds#Deepfly"
        embed = discord.Embed(
            description=f"""
                        ### [How to bind and configure deepfly]({url}):
                        We highly recommended to read this [article]({url}).
                        
                        If you prefer to not read the article:
                        Move the attached text file to your config directory
                        and then type: `exec deepfly.txt` into the ingame console (F1).
                        
                        To toggle deepfly on/off, press "C" on your keyboard.
                        """,
            colour=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply( message=ctx.message, file=file, embed=embed)
            await ctx.send(file=bindconfig)

    @commands.command()
    async def skins(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        embed = discord.Embed(
            title="How can I get other players to see the skin that I created?",
            description="There are two ways to get other players to see your custom skin: \n\n"
            "**Method 1:** \nThey need to manually add your skin to their game files by "
            "pasting it in the skins folder in the config directory. \n\n"
            "**Method 2:** \nYour skin gets added to the official SkinDB. \n\n"
            "For more info on how to get your skin uploaded to the SkinDB, "
            f"visit this channel: <#{Channels.SKIN_INFO}>",
            colour=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command()
    async def binds(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        embed = discord.Embed(
            title="How do I bind x ?", description="", colour=discord.Colour.blurple()
        )
        embed.add_field(
            name="wiki.ddnet.org",
            value="Content: \nThorough explanation how binds work, Deepfly, 45° Aim bind, Rainbow Tee \n\n"
            "**URL:** \n"
            "[wiki.ddnet.org](https://wiki.ddnet.org/wiki/Binds)",
        )
        embed.add_field(
            name="DDNet Forums",
            value="Content: \nClient-, Chat-, Dummy-, Mouse-, Player- and RCON settings \n\n"
            "**URL:** \n"
            "[forum.ddnet.org](https://forum.ddnet.org/viewtopic.php?f=16&t=2537)",
        )
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command()
    async def crash(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        embed = discord.Embed(
            title="Crash Logs",
            description="To help us debug the cause for your crash, "
            "provide the following information: \n"
            "* Operating System \n"
            " - Windows, Linux or macOS? \n"
            " - 32Bit or 64Bit? \n"
            "* Client version \n"
            "* Steam or Standalone? \n"
            " - Steam: Stable, Nightly or releasecandidate beta? \n"
            "* Upload the most recent crash log file from your dumps "
            "folder in the config directory (drag and drop it here).",
            colour=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command(aliases=["kog", "login", "registration"])
    async def kog_login(self, ctx: commands.Context):
        file = discord.File("data/avatar.png", filename="avatar.png")
        embed = discord.Embed(
            title=f'{"KoG affiliation" if ctx.invoked_with == "kog" else "KoG Account Registration and Migration"}',
            description="First and foremost: DDNet and KoG aren't affiliated.\n\n"
            "If you need help on a server related to KoG, "
            "join their Discord server by clicking on the link below.",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="URL:", value="https://discord.kog.tw/", inline=False)
        if ctx.invoked_with in ["login", "registration"]:
            embed.add_field(
                name="Registration process:",
                value="https://discord.com/channels/342003344476471296/941355528242749440/1129043200527569018",
                inline=True,
            )
            embed.add_field(
                name="Migration process:",
                value="https://discord.com/channels/342003344476471296/941355528242749440/1129043332211945492",
                inline=True,
            )
            embed.add_field(
                name="How to login on KoG servers:",
                value="https://discord.com/channels/342003344476471296/941355528242749440/1129043447517564978",
                inline=True,
            )
            embed.add_field(
                name="Video Guide:",
                value="https://www.youtube.com/watch?v=d1kbt-srlac",
                inline=False,
            )
        embed.set_footer(text="You are not required to log-in on a DDNet server.")
        embed.set_thumbnail(url="attachment://avatar.png")
        with contextlib.suppress(discord.Forbidden):
            await self.bot.reply(message=ctx.message, file=file, embed=embed)

    @commands.command(aliases=["translator", "english"])
    async def deepl(self, ctx: commands.Context):
        await self.bot.reply(message=ctx.message, content=
            "Hi! Most of us communicate in English. "
            "If you’re having trouble with English, use <https://www.deepl.com/en/translator> to help you out."
        )

    @commands.command(aliases=["failed-inserts", "missing-rank", "missing-save"])
    async def failed_inserts(self, ctx: commands.Context):
        await self.bot.reply(message=ctx.message, content=
            "In-game Ranks and saves may occasionally fail to be inserted in our database. "
            "This can happen for various reasons, including poor connectivity to our "
            "main database due to lag or hoster issues. "
            "However, there's no need to worry! The ranks and saves are stored locally "
            "and will be attempted to be inserted again within the next 24 hours."
        )

    @commands.command(aliases=["gfx", "missing-text", "no-text", "missing-ui", "no-ui"])
    async def gfx_troubleshoot(self, ctx: commands.Context):
        await self.bot.reply(message=ctx.message, content=
            "https://wiki.ddnet.org/wiki/GFX_Troubleshooting#Some_text_is_invisible_with_the_Vulkan_backend"
        )

    @commands.command(aliases=["utc", "utc-time", "utc-now"])
    async def utc_now(self, ctx: commands.Context):
        await self.bot.reply(message=ctx.message, content=
            f"Current UTC Time: `{utcnow().strftime('%YY-%mM-%dD %HH:%MM')}`"
        )


async def setup(bot: commands.bot):
    await bot.add_cog(HelperCommands(bot))
