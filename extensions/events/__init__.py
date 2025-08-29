import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, button
import logging

from .holidays import halloween, christmas, easter
from constants import Guilds, Roles

from utils.text import datetime_to_unix

log = logging.getLogger()


class BannerIconEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="contest", description="The Banner menu with buttons")
    @app_commands.choices(theme=[
        app_commands.Choice(name="Christmas", value="christmas"),
        app_commands.Choice(name="Halloween", value="halloween"),
        app_commands.Choice(name="Easter", value="easter")
    ])
    @app_commands.describe(
        theme="Choose which theme the event is supposed to be.",
        submission_end="The end date of the submission period. Expected Format: YYYY/MM/DD HH:MM || Example: 2025/04/10 15:21",
        voting_end="The end date of the voting period. Expected Format: YYYY/MM/DD HH:MM || Example: 2025/04/10 15:21",
    )
    async def art_contest(
            self,
            interaction: discord.Interaction,
            theme: str,
            submission_end: str,
            voting_end: str = None
    ):
        try:
            if theme == "christmas":
                embed, file = christmas.Christmas(
                    self.bot,
                    sub_end=datetime_to_unix(submission_end),
                    vote_end=datetime_to_unix(voting_end)
                )

            elif theme == "halloween":
                embed, file = halloween.Halloween(
                    self.bot,
                    sub_end=datetime_to_unix(submission_end),
                    vote_end=datetime_to_unix(voting_end)
                )

            elif theme == "easter":
                embed, file = easter.Easter(
                    self.bot,
                    sub_end=datetime_to_unix(submission_end),
                    vote_end=datetime_to_unix(voting_end)
                )

        except ValueError as e:
            await interaction.response.send_message(content=e, ephemeral=True)
            return

        await interaction.channel.send(
            embed=embed, file=file, view=Submit(self.bot)  # noqa
        )

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(view=Submit(self.bot))
        self.bot.add_view(view=CloseButton(self.bot))
        self.bot.add_view(view=ConfirmButton(self.bot))


class Submit(discord.ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @staticmethod
    async def has_active_submission(user: discord.User, category: discord.CategoryChannel, _type: str):
        return next(
            (
                channel
                for channel in category.text_channels
                if channel.topic is not None
                   and f"Submission author: <@{user.id}>" in channel.topic
                   and f"Ticket type: {_type}" in channel.topic  # Check ticket type in the topic
            ),
            None,
        )

    @discord.ui.button(label="Submit Banner", style=discord.ButtonStyle.success, custom_id="BannerMenu:Banner")
    async def banner_submit(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            interaction.guild.get_role(Roles.BANNER_CURATOR): discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        }
        category = interaction.channel.category
        # category = interaction.guild.get_channel(Channels.CAT_BANNER_EVENT)
        channel = await self.has_active_submission(
            interaction.user,
            category=category,
            _type="Banner"
        )

        if channel:
            await interaction.followup.send(  # noqa
                content=f"You already have an open submission: {channel.mention}",
                ephemeral=True,
            )
            return

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"banner-{interaction.user.name}",
            category=category,
            position=category.channels[-1].position + 0,
            overwrites=overwrites,
            topic=f"Submission author: {interaction.user.mention} Ticket type: Banner",
        )

        embed = discord.Embed(title="Submission", color=discord.Colour.blurple())
        embed.add_field(
            name=f"",
            value=f"Hello {interaction.user.mention},\n"
                  f"thanks for your banner submission!\n\n"
                  f"This is your channel to submit your banner. "
                  f"The criteria will be checked here before all images are moved to a voting channel.",
            inline=False,
        )

        embed2 = discord.Embed(title="", colour=16776960)
        embed2.add_field(
            name="",
            value="If you opened this channel by mistake, use the close button below.",
            inline=False,
        )

        message = await ticket_channel.send(
            embeds=[embed, embed2],
            view=CloseButton(interaction.client),
        )

        await interaction.followup.send(  # noqa
            f"<@{interaction.user.id}> your submission channel has been created: {message.jump_url}",
            ephemeral=True,
        )
        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a Banner submission channel.'
        )

    @discord.ui.button(label="Submit Icon", style=discord.ButtonStyle.success, custom_id="BannerMenu:Icon")
    async def icon_submit(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            interaction.guild.get_role(Roles.BANNER_CURATOR): discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        }

        category = interaction.channel.category
        # category = interaction.guild.get_channel(Channels.CAT_BANNER_EVENT)
        channel = await self.has_active_submission(interaction.user, category=category, _type="Icon")
        if channel:
            await interaction.followup.send(  # noqa
                content=f"You already have an open submission: {channel.mention}",
                ephemeral=True,
            )
            return

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"icon-{interaction.user.name}",
            category=category,
            position=category.channels[-1].position + 0,
            overwrites=overwrites,
            topic=f"Submission author: {interaction.user.mention} Ticket type: Icon",
        )

        embed = discord.Embed(title="Submission", color=discord.Colour.blurple())
        embed.add_field(
            name=f"",
            value=f"Hello {interaction.user.mention},\n"
                  f"thanks for your icon submission!\n\n"
                  f"This is your channel to submit your icon. "
                  f"The criteria will be checked here before all images are moved to a voting channel.",
            inline=False,
        )

        embed2 = discord.Embed(title="", colour=16776960)
        embed2.add_field(
            name="",
            value="If you opened this channel by mistake, use the close button below.",
            inline=False,
        )

        message = await ticket_channel.send(
            embeds=[embed, embed2],
            view=CloseButton(interaction.client),
        )

        await interaction.followup.send(  # noqa
            f"<@{interaction.user.id}> your submission channel has been created: {message.jump_url}",
            ephemeral=True,
        )
        log.info(
            f'{interaction.user} (ID: {interaction.user.id}) created a Banner submission channel.'
        )


class CloseButton(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.blurple,
        custom_id="MainMenu:close_submission",
    )
    async def t_close(self, interaction: discord.Interaction, _: Button):
        """Button which closes a Ticket"""

        await interaction.response.send_message(  # noqa
            content="Are you sure you want to remove the submission?",
            ephemeral=True,
            view=ConfirmButton(self.bot),
        )


class ConfirmButton(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.green,
        custom_id="confirm:close_submission",
    )
    async def confirm(self, interaction: discord.Interaction, _: Button):
        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if interaction.response.is_done():  # noqa
            await interaction.edit_original_response(content="Removing Submission...")
            await interaction.channel.delete()
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BannerIconEvents(bot))
