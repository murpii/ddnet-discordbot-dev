from typing import Optional
import discord

from extensions.management.moderator.manager import MemberInfo


class UntimeoutButton(discord.ui.Button):
    def __init__(self, bot, member: discord.abc.User):
        super().__init__(label="Remove Timeout", style=discord.ButtonStyle.success)  # noqa
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This action can only be used in a guild.",
                ephemeral=True,
            )
            return

        member = guild.get_member(self.member.id)
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Cannot clear timeout: target is not in the guild.",
                ephemeral=True,
            )
            return

        try:
            await member.timeout(None, reason=f"Timeout cleared by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I do not have permission to clear this timeout.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "HTTPException: Clearing timeout failed. Try again later.",
                ephemeral=True,
            )
            return

        notice = f"Timeout for {member.mention} has been cleared."
        info: Optional[MemberInfo] = await self.db.fetch_user_info(member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.response.edit_message(view=NoUserInfoView(notice=notice))
            return

        await interaction.response.edit_message(
            view=UserInfoView(self.bot, info, interaction.user, notice=notice)
        )
