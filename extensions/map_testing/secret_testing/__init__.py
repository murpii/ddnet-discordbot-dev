import discord
from discord.ext import commands
import logging
import os

import shlex

from extensions.map_testing.submission import Submission
from constants import Guilds, Channels, Roles

from utils.misc import run_process_shell, check_os

from io import BytesIO
from typing import Optional

log = logging.getLogger()


class Secret(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    DIR = "data/map-testing"

    @commands.Cog.listener("on_message")
    async def pin_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return

        if message.channel.category.id != Channels.CAT_SECRETS:
            return

        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith(".map"):
                    try:
                        await message.pin()
                    except discord.HTTPException as e:
                        log.error(f"Failed to pin message: {e}")
                    break

    @commands.command(name="optimize")
    async def optimize(self, ctx: commands.Context):
        if ctx.guild.id != Guilds.DDNET:
            return

        if ctx.message.channel.category.id != Channels.CAT_SECRETS:
            return

        args = ["--remove-everything-unused", "--shrink-tiles-layers"]
        stdout, file = await Submission((await ctx.channel.pins())[0]).edit_map(*args)

        await ctx.channel.send(
            content=f"Optimized version attached, {ctx.author.mention}. Changelog: \n```{stdout}```\n"
            if stdout
            else "Optimized version:",
            file=file,
            allowed_mentions=discord.AllowedMentions(users=False)
        )

    @commands.command(name="twmap-edit")
    async def twmap_edit(self, ctx: commands.Context, *, options: str):
        try:
            options = shlex.split(options)
        except ValueError as e:
            await ctx.send(f"Invalid arguments: {e}")
            return

        pins = await ctx.channel.pins()
        print(options)
        try:
            stdout, file = await Submission(pins[0]).edit_map(*options)
        except RuntimeError as e:
            await ctx.channel.send(str(e))
            return

        if stdout:
            stdout = f"```{stdout}```"

        if file is None:
            await ctx.channel.send(stdout)
        else:
            await ctx.channel.send(stdout, file=file)

    @commands.command(name="preview")
    async def generate_thumbnail(self, ctx: commands.Context) -> Optional[discord.File]:
        if ctx.guild.id != Guilds.DDNET:
            return

        if ctx.message.channel.category.id != Channels.CAT_SECRETS:
            return

        pins = await ctx.channel.pins()

        if not pins or not pins[0].attachments:
            await ctx.send("No pinned messages or attachments found.")
            return

        attachment = pins[0].attachments[0]

        if not attachment.filename.endswith(".map"):
            await ctx.send("Pinned message does not contain a .map file.")
            return

        buf = BytesIO(await attachment.read())
        tmp = f'{self.DIR}/{attachment.filename}'
        with open(tmp, 'wb') as f:
            f.write(buf.getvalue())

        _, ext = check_os()

        try:
            stdout, stderr = await run_process_shell(f'{self.DIR}/twgpu-map-photography{ext} {tmp}')
        except Exception as e:
            log.error(e)
            await ctx.send("Error occurred while generating the image.")
            return
        else:
            log.info("stdout: %s", stdout)
            if stderr:
                log.error("stderr: %s", stderr)

        base_name, _ = os.path.splitext(attachment.filename)
        image_filename = f'{base_name}.png'
        try:
            with open(image_filename, 'rb') as f:
                image_buf = BytesIO(f.read())
        except FileNotFoundError as e:
            log.info(e)
            await ctx.send("Generated image not found.")
            return

        await ctx.send(file=discord.File(image_buf, filename=f'{pins[0].id}.png'))
        os.remove(tmp)
        os.remove(image_filename)


async def setup(bot: commands.Bot):
    await bot.add_cog(Secret(bot))
