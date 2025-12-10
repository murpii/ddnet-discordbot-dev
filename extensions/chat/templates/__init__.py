import contextlib
import re
import os
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands

from utils.checks import ddnet_only
from . import dictionary
from constants import Guilds, Channels

DIR = "data/assets/graphics"


# noinspection PyUnresolvedReferences
class Botscribe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="echo",
        with_app_command=True,
        description="Sends a message via bot",
        usage="$echo Optional:<highlight_mentions(True/False)> <Text>")
    @commands.check(ddnet_only)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.describe(
        text="The new message content",
        highlight_mentions="Whether to highlight the roles in the text if any exists", )
    async def echo(self, ctx: commands.Context, highlight_mentions: Optional[bool] = False, *, text: str):
        # TODO: Add a way to echo images/attachments
        await ctx.defer(ephemeral=True)

        if not highlight_mentions:
            with contextlib.suppress(discord.errors.Forbidden):
                await ctx.channel.send(
                    content=text, allowed_mentions=discord.AllowedMentions(roles=False)
                )
        else:
            with contextlib.suppress(discord.errors.Forbidden):
                await ctx.channel.send(text)

        with contextlib.suppress(discord.NotFound):
            if ctx.interaction:
                await ctx.interaction.delete_original_response()
            else:
                await ctx.message.delete()

    @app_commands.command(
        name="less",
        description="Reads the raw message content and echos it back")
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.describe(
        message_id="The message ID of the discord message",
        encase_urls="Whether URLs in the message content should be encased in angle brackets")
    async def less(
            self,
            interaction: discord.Interaction,
            message_id: str,
            encase_urls: bool = False,
            escape_markdown: bool = False
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        try:
            message = await interaction.channel.fetch_message(int(message_id))
            message_fmt = message.content
            if escape_markdown:
                message_fmt = discord.utils.escape_markdown(message.content)
            if encase_urls:
                message_fmt = re.sub(r'(https://[^\s)]+)', r'<\1>', message_fmt)
            await interaction.followup.send(f"```{message_fmt}```")
        except discord.NotFound:
            await interaction.followup.send(
                content="Could not find the mentioned message. "
                        "Ensure the command is used in the same channel as the message you're trying to fetch."
            )

    @commands.hybrid_command(
        name="edit",
        with_app_command=True,
        description="Updates a message from the bot",
        usage="edit <messageID> <Text>")
    @commands.check(ddnet_only)
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.describe(
        message_id="The message ID of the discord message to be updated",
        text="The new message content")
    async def edit(self, ctx: commands.Context, message_id: str, *, text: str):
        await ctx.defer(ephemeral=True)

        content = getattr(dictionary, text) if hasattr(dictionary, text) else text
        message_to_edit = await ctx.channel.fetch_message(int(message_id))
        await message_to_edit.edit(content=content)
        with contextlib.suppress(discord.NotFound):
            if ctx.interaction:
                await ctx.interaction.delete_original_response()
            else:
                await ctx.message.delete()


@app_commands.guilds(discord.Object(Guilds.DDNET))
@app_commands.default_permissions(administrator=True)
class Template(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    async def send_messages(self, channel_id, messages):
        channel = self.bot.get_channel(channel_id)
        await channel.purge()

        description = None

        for filename, message_attr in messages:
            if filename is not None:
                path = os.path.join(DIR, filename)
                await channel.send(file=discord.File(path, filename=filename))

            if message_attr is not None:
                description = getattr(dictionary, message_attr, None)

            if description is not None:
                await channel.send(
                    content=description,
                    allowed_mentions=discord.AllowedMentions(roles=False)
                )

    @app_commands.command(
        name="welcome",
        description="Sends all relevant messages (found in dictionary.py) and images to the welcome channel.",
    )
    async def welcome(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        await self.send_messages(
            Channels.WELCOME,
            [
                ("welcome_main.png", "welcome_main"),
                ("welcome_rules.png", "welcome_rules"),
                ("welcome_channels.png", "welcome_channel_listing"),
                ("welcome_links.png", "welcome_ddnet_links"),
                ("welcome_roles.png", "welcome_ddnet_roles"),
                ("welcome_communities.png", "welcome_community_links"),
            ],
        )
        await interaction.followup.send("Done")

    @app_commands.command(
        name="testing-info",
        description="Sends all relevant messages (found in dictionary.py) and images to the testing info channel.",
    )
    @app_commands.guilds(discord.Object(Guilds.DDNET))
    @app_commands.default_permissions(administrator=True)
    async def testing_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        await self.send_messages(
            Channels.TESTING_INFO,
            [
                ("testing_map_testing.png", None),
                ("testing_main.png", "testing_info_header"),
                (None, "testing_info"),
                (None, "testing_channel_access"),
            ],
        )

        channel = self.bot.get_channel(Channels.TESTING_INFO)
        reaction_message = None
        async for message in channel.history(limit=1):
            reaction_message = message
            break

        await reaction_message.add_reaction("✅")
        await interaction.followup.send("Done")


async def setup(bot):
    await bot.add_cog(Botscribe(bot))
    await bot.add_cog(Template(bot))
