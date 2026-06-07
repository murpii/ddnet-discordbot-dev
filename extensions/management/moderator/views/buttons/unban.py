from typing import Optional
import discord

from extensions.management.moderator.manager import MemberInfo, ModAction, PendingAction


class UnbanButton(discord.ui.Button):
    def __init__(self, bot, member: discord.abc.User):
        super().__init__(label="Unban", style=discord.ButtonStyle.success)  # noqa
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

        try:
            self.db.actions[self.member.id] = PendingAction(
                moderator=interaction.user,
                action=ModAction.UNBAN,
                reason="No reason given.",
            )
            await guild.unban(discord.Object(id=self.member.id), reason=f"Unbanned by {interaction.user}")
        except discord.NotFound:
            # already unbanned
            pass
        except discord.Forbidden:
            await interaction.response.send_message(
                "I do not have permission to unban this user.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "HTTPException: Unban failed. Try again later.",
                ephemeral=True,
            )
            return

        notice = f"{self.member.mention} has been unbanned."
        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.response.edit_message(view=NoUserInfoView(notice=notice))
            return

        await interaction.response.edit_message(view=UserInfoView(self.bot, info, notice=notice))
