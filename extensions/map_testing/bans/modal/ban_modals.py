from typing import Optional
import discord
import logging

from utils.changelog import ChangelogPaginator
from constants import Guilds

log = logging.getLogger("mt")

class BaseBanModal(discord.ui.Modal):
    def __init__(self, bot, title: str):
        super().__init__(title=title, timeout=None)
        self.bot = bot
        self.guild = self.bot.get_guild(Guilds.DDNET)
        self.testing_bans = self.bot.get_cog("TestingBans")

    async def get_user_from_input(self, interaction: discord.Interaction, user_input: str) -> Optional[discord.Member]:
        try:
            user = await self.bot.get_or_fetch_member(guild=self.guild, user_id=int(user_input))
            if user is not None:
                return user
            await interaction.response.send_message("User not found.", ephemeral=True)
            return None
        except ValueError:
            await interaction.response.send_message(
                content="The identifier must be a valid user ID.",
                ephemeral=True
            )
            return None
        except discord.NotFound:
            await interaction.response.send_message(
                content="User not found. Please ensure the user ID is correct.",
                ephemeral=True
            )
            return None
        except discord.HTTPException as e:
            await interaction.response.send_message(
                content=f"An error occurred: {e}",
                ephemeral=True
            )
            return None
        except Exception as e:
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

        try:
            await self.testing_bans.ban_or_unban(user=user, ban=ban)
        except PermissionError as e:
            await interaction.followup.send(e)
            return

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
        if not user:
            return

        try:
            await self.apply_ban_change(
                interaction,
                user=user,
                ban=True,
                reason=self.reason.value,
                changelog_paginator=self.changelog_paginator
            )
        except Exception as e:
            await interaction.followup.send(e)


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
        if not user:
            return

        try:
            await self.apply_ban_change(
                interaction,
                user,
                ban=False,
                changelog_paginator=self.changelog_paginator
            )
        except (PermissionError, ValueError) as e:
            await interaction.followup.send(e)