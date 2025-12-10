from typing import Optional
import discord

from extensions.moderator.manager import MemberInfo, ModAction, PendingAction
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info


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

        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)
        if not info:
            await interaction.response.edit_message(
                content=f"User {self.member.mention} has been unbanned.",
                embeds=[NoMemberInfoEmbed()],
                view=None,
            )
            return

        has_any_entries = bool(
            info.timeout_reasons or info.kick_reasons or info.ban_reasons
        )

        from extensions.moderator.views.info import MemberModerationView
        view = MemberModerationView(
            bot=interaction.client,
            info=info,
            can_remove_entries=has_any_entries,
        )
        updated_embeds = full_info(info)

        await interaction.response.edit_message(
            content=f"User {self.member.mention} has been unbanned.",
            embeds=updated_embeds,
            view=view,
        )
