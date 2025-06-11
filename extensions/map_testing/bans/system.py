from typing import Union, Optional

import discord
from discord.ext import commands
import logging

from extensions.map_testing.bans.view import BanViews
from utils.checks import is_staff
from utils.changelog import ChangelogPaginator
from constants import Guilds, Channels, Messages, Roles

log = logging.getLogger("mt")


class TestingBans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.testing_banned_users = {}
        self.changelog: int = Messages.TESTING_BANS_CHANGELOG
        self.bans_embed: int = Messages.TESTING_BANS_EMBED
        self.changelog_paginator: ChangelogPaginator = ...
        self.extra_embed = ...

    async def setup_changelog_paginator(self):
        """Setup the changelog paginator."""
        bans_channel: discord.TextChannel = self.bot.get_channel(Channels.TESTER_BANS)
        if bans_channel is None:
            raise ValueError(f"{self.__cog_name__} ERROR: Bans channel not set up.")
        
        try:
            self.changelog = await bans_channel.fetch_message(self.changelog)
        except discord.NotFound as e:
            raise ValueError(
                f"{self.__cog_name__} ERROR: Ban changelog embed not set up. "
                f"Use \"$changelog_embed\" to set up the bans changelog message and assign the message ID in constants.py"
            ) from e

        self.changelog_paginator = ChangelogPaginator(
            self.bot,
            changelog=self.changelog,
            channel=bans_channel,
            embeds=self.extra_embed
        )
        await self.changelog_paginator.get_data(message=self.changelog)
        await self.changelog_paginator.assign_changelog_message(message=self.changelog)
        self.bot.add_view(view=self.changelog_paginator, message_id=self.changelog.id)
        await self.changelog_paginator.update_changelog()

    async def load_banned_users(self):
        query = """
        SELECT * FROM discordbot_testing_bans WHERE banned_bool is TRUE
        """
        banned_users = await self.bot.fetch(query, fetchall=True)
        for user_id, mod_id, reason, active_flag, timestamp in banned_users:
            guild = self.bot.get_guild(Guilds.DDNET)
            user = await self.bot.get_or_fetch_member(guild=guild, user_id=user_id)
            moderator = await self.bot.get_or_fetch_member(guild=guild, user_id=mod_id)
            if user:
                self.bot.testing_banned_users[user] = {
                    "moderator": moderator,
                    "reason": reason,
                    "active_ban": bool(active_flag),
                    "timestamp": timestamp,
                }

    async def load_bans_embed(self):
        bans_channel: discord.message = self.bot.get_channel(Channels.TESTER_BANS)
        if bans_channel is None:
            raise ValueError(f"{self.__cog_name__} ERROR: Bans channel not set up.")
        
        try:
            self.bans_embed = await bans_channel.fetch_message(self.bans_embed)
        except discord.NotFound as e:
            raise ValueError(
                f"{self.__cog_name__} ERROR: Bans embed not set up. "
                f"Use \"$bans_embed\" to set up the bans embed and assign the message ID in constants.py"
            ) from e

        self.bot.add_view(
            view=BanViews(self.bot, changelog_paginator=self.changelog_paginator, bans_embed=self.bans_embed),
            message_id=Messages.TESTING_BANS_EMBED
        )
        await self.changelog_paginator.update_changelog()  # DEBUG

    async def extra_bans_embed(self) -> discord.Embed:
        desc = [
            f"{user.mention} [ID: {user.id}]: {info['reason']}"
            for user, info in self.bot.testing_banned_users.items()
            if info.get("active_ban")
        ]
        self.extra_embed = discord.Embed(
            title="Currently Banned Users",
            description="\n".join(desc) if desc else "No active bans."
        )
        self.extra_embed.set_footer(text="Format: @mention [ID]: REASON")
        return self.extra_embed

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.load_banned_users()
            await self.extra_bans_embed()
            await self.setup_changelog_paginator()
            await self.load_bans_embed()
        except Exception as e:
            log.warning(f"Unloading {self.__cog_name__} cog due to error:\n{e}")
            await self.bot.unload_extension("extensions.map_testing.bans")

    async def ban_or_unban(self, user: Union[discord.User, discord.Member], ban: bool = True):
        landing_channels = [Channels.TESTING_INFO, Channels.TESTING_SUBMIT]
        for ids in landing_channels:
            channel = self.bot.get_channel(ids)
            try:
                if ban:
                    overwrites = channel.overwrites_for(user)
                    overwrites.view_channel = False
                    await channel.set_permissions(user, overwrite=overwrites)
                else:
                    await channel.set_permissions(user, overwrite=None)
            except discord.Forbidden as e:
                log.exception(e)
                raise PermissionError(
                    f"Failed to {'ban' if ban else 'unban'} user {user} from channel #{channel.name}: {e}"
                ) from e

        for map_channel in self.bot.map_channels.values():
            try:
                if ban:
                    overwrites = map_channel.overwrites_for(user)
                    overwrites.view_channel = False
                    await map_channel.set_permissions(user, overwrite=overwrites)
                else:
                    await map_channel.set_permissions(user, overwrite=None)
            except discord.Forbidden as e:
                log.exception(e)
                raise PermissionError(
                    f"Failed to {'ban' if ban else 'unban'} user {user} from channel #{channel.name}: {e}"
                ) from e

        guild = self.bot.get_guild(Guilds.DDNET)
        testing_role = guild.get_role(Roles.TESTING)
        member = guild.get_member(user.id) or await guild.fetch_member(user.id)
        
        if ban and testing_role in member.roles:
            await member.remove_roles(testing_role)


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != Guilds.DDNET or member.bot:
            return
        if member in self.bot.testing_banned_users and self.bot.testing_banned_users[member]["active_ban"]:
            await self.ban_or_unban(member, ban=True)

    @commands.check(lambda ctx: is_staff(ctx.author, [Roles.ADMIN]))
    @commands.command(name="bans_embed")
    async def bans_embed(self, ctx):
        """Sends the initial embed to track banned users."""
        embed = discord.Embed(
            title="Ban User from Testing",
            description='If you wish to remove someone Testing, you can use the buttons bellow. '
                        'All bans are audited in the Embed above.',
            color=discord.Color.red(),
        )
        await ctx.send(
            embed=embed,
            view=BanViews(
                self.bot,
                changelog_paginator=self.changelog_paginator,
                bans_embed=self.bans_embed,  # noqa
            )
        )

    @commands.check(lambda ctx: is_staff(ctx.author, [Roles.ADMIN]))
    @commands.command(name="changelog_embed")
    async def changelog_embed(self, ctx):
        data = ()
        paginator = ChangelogPaginator(data)
        await ctx.send(embed=paginator.format_changelog_embed(), view=paginator)
