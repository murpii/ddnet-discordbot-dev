from typing import Union, Optional

import discord
from discord.ui import Button
from discord.ext import commands
import logging

from constants import Guilds, Channels, Messages, Roles
from utils.checks import is_staff
from utils.changelog import ChangelogPaginator

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
        self.changelog = await bans_channel.fetch_message(self.changelog)
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
        self.bans_embed = await bans_channel.fetch_message(self.bans_embed)
        self.bot.add_view(
            view=Buttons(self.bot, changelog_paginator=self.changelog_paginator, bans_embed=self.bans_embed),
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
        await self.load_banned_users()
        await self.extra_bans_embed()
        await self.setup_changelog_paginator()
        await self.load_bans_embed()

    async def ban_or_unban(self, user: Union[discord.User, discord.Member], ban: bool = True):
        guild = self.bot.get_guild(Guilds.DDNET)
        testing_role = guild.get_role(Roles.TESTING)
        member = guild.get_member(user.id) or await guild.fetch_member(user.id)

        if ban and testing_role in member.roles:
            await member.remove_roles(testing_role)

        landing_channels = [Channels.TESTING_INFO, Channels.TESTING_SUBMIT]
        for channel_id in landing_channels:
            channel = self.bot.get_channel(channel_id)
            try:
                overwrites = channel.overwrites_for(user)
                overwrites.view_channel = not ban
                await channel.set_permissions(user, overwrite=overwrites)
            except Exception as exc:
                log.error(f"Failed to {'ban' if ban else 'unban'} user {user} from channel #{channel.name}: {exc}")

        for map_channel in self.bot.map_channels.values():
            try:
                overwrites = map_channel.overwrites_for(user)
                overwrites.view_channel = not ban
                await map_channel.set_permissions(user, overwrite=overwrites)
            except Exception as exc:
                log.error(f"Failed to {'ban' if ban else 'unban'} user {user} from channel #{map_channel.name}: {exc}")


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
            view=Buttons(
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


class Buttons(discord.ui.View):
    def __init__(
            self,
            bot,
            changelog_paginator: ChangelogPaginator,
            bans_embed: discord.Message,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, lambda i: i.user.id)
        self.changelog_paginator = changelog_paginator
        self.bans_embed = bans_embed

    async def interaction_check(self, interaction: discord.Interaction):
        if not is_staff(
                interaction.user,
                roles=[
                    Roles.ADMIN,
                    Roles.TESTER, Roles.TESTER_EXCL_TOURNAMENTS,
                    Roles.TRIAL_TESTER, Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
                    Roles.MODERATOR, Roles.DISCORD_MODERATOR
                ]
        ):
            await interaction.response.send_message("You're missing the required Role to do that!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, custom_id="TestingBan:ban")
    async def t_ban(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.send_modal(  # noqa
            BanModal(
                self.bot,
                changelog_paginator=self.changelog_paginator,
                # bans_embed=self.bans_embed,
            )
        )

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.primary, custom_id="TestingBan:unban")
    async def t_unban(self, interaction: discord.Interaction, _: Button):  # noqa
        await interaction.response.send_modal(  # noqa
            UnbanModal(
                self.bot,
                changelog_paginator=self.changelog_paginator,
            )
        )  # noqa


class BaseBanModal(discord.ui.Modal):
    def __init__(self, bot, title: str):
        super().__init__(title=title, timeout=None)
        self.bot = bot
        self.guild = self.bot.get_guild(Guilds.DDNET)
        self.testing_bans = self.bot.get_cog("TestingBans")

    async def get_user_from_input(self, interaction: discord.Interaction, user_input: str) -> Optional[discord.Member]:
        try:
            user_id = int(user_input)
            return await self.bot.get_or_fetch_member(guild=self.guild, user_id=user_id)
        except ValueError:
            await interaction.response.send_message(
                content="The identifier must be a valid user ID.",
                ephemeral=True
            )
        except discord.NotFound:
            await interaction.response.send_message(
                content="User not found. Please ensure the user ID is correct.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                content=f"An error occurred: {e}",
                ephemeral=True
            )
        return None

    async def apply_ban_change(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        *,
        ban: bool,
        reason: Optional[str] = None,
        changelog_paginator: Optional[ChangelogPaginator] = None
    ):
        banned_users = self.bot.testing_banned_users
        currently_banned = user in banned_users and banned_users[user]["active_ban"]

        if ban and currently_banned:
            await interaction.response.send_message(
                content=f"User {user.mention} is already banned from testing.",
                ephemeral=True
            )
            return
        elif not ban and not currently_banned:
            await interaction.response.send_message(
                content=f"User {user.mention} is not currently banned from testing.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa

        if ban:
            query = """
                INSERT INTO discordbot_testing_bans (
                    banned_user_id, banned_by, ban_reason, banned_bool
                )
                VALUES (%s, %s, %s, TRUE)
                ON DUPLICATE KEY UPDATE
                    banned_by = VALUES(banned_by),
                    ban_reason = VALUES(ban_reason),
                    banned_bool = TRUE
            """

            await self.bot.upsert(query, user.id, interaction.user.id, reason)

            banned_users[user] = {
                "moderator": interaction.user,
                "reason": reason,
                "active_ban": True,
                "timestamp": discord.utils.utcnow()
            }

            if changelog_paginator:
                await changelog_paginator.add_changelog(
                    interaction.channel,
                    interaction.user,
                    category="MapTesting/Bans",
                    string=f"{user.mention} was banned for \"{reason}\""
                )

        else:
            banned_users[user]["active_ban"] = False

            query = """
                UPDATE discordbot_testing_bans
                SET banned_bool = FALSE
                WHERE banned_user_id = %s
            """
            await self.bot.upsert(query, user.id)

            if changelog_paginator:
                await changelog_paginator.add_changelog(
                    interaction.channel,
                    interaction.user,
                    category="MapTesting/Bans",
                    string=f"{user.mention} was unbanned."
                )

        await self.testing_bans.ban_or_unban(user=user, ban=ban)

        updated_embed = await self.testing_bans.extra_bans_embed()
        await self.testing_bans.changelog_paginator.update_extras(updated_embed)
        await self.testing_bans.changelog_paginator.update_changelog()

        await interaction.followup.send(
            content=f"User {user.mention} has been {'banned' if ban else 'unbanned'} from testing.",
            ephemeral=True
        )


class BanModal(BaseBanModal):
    def __init__(self, bot, changelog_paginator: ChangelogPaginator):
        super().__init__(bot=bot, title="Ban From Testing")
        self.changelog_paginator = changelog_paginator

        self.user_to_ban = discord.ui.TextInput(
            label="User ID",
            placeholder="Enter user ID to ban",
            max_length=19
        )

        self.reason = discord.ui.TextInput(
            label="Reason",
            placeholder="Enter ban reason",
            max_length=24
        )

        self.add_item(self.user_to_ban)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        user = await self.get_user_from_input(interaction, self.user_to_ban.value)
        if user:
            await self.apply_ban_change(
                interaction,
                user,
                ban=True,
                reason=self.reason.value,
                changelog_paginator=self.changelog_paginator
            )


class UnbanModal(BaseBanModal):
    def __init__(self, bot, changelog_paginator: ChangelogPaginator):
        super().__init__(bot=bot, title="Unban From Testing")
        self.changelog_paginator = changelog_paginator

        self.user_to_unban = discord.ui.TextInput(
            label="User ID",
            placeholder="Enter user ID to unban",
            max_length=19
        )

        self.add_item(self.user_to_unban)

    async def on_submit(self, interaction: discord.Interaction):
        user = await self.get_user_from_input(interaction, self.user_to_unban.value)
        if user:
            await self.apply_ban_change(
                interaction,
                user,
                ban=False,
                changelog_paginator=self.changelog_paginator
            )


async def setup(bot):
    await bot.add_cog(TestingBans(bot))
