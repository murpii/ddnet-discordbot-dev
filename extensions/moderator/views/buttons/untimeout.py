from typing import Optional
import discord

from extensions.moderator.manager import MemberInfo
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info


class UntimeoutButton(discord.ui.Button):
    def __init__(self, bot, member: discord.abc.User):
        super().__init__(label="Untimeout", style=discord.ButtonStyle.success)  # noqa
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

        # Refresh MemberInfo after clearing timeout
        info: Optional[MemberInfo] = await self.db.fetch_user_info(member)
        if not info:
            await interaction.response.edit_message(
                content=f"Timeout for {member.mention} has been cleared.",
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
            content=f"Timeout for {member.mention} has been cleared.",
            embeds=updated_embeds,
            view=view,
        )
