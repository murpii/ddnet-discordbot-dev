from typing import Optional

import discord

from extensions.management.moderator.manager import MemberInfo, PendingAction, ModAction
from utils.containers import NoticeView
from utils.misc import DELETE_HISTORY_SECONDS
from utils.text import clip
from extensions.management.moderator.views.modals.ban import DELETE_HISTORY_OPTIONS


class KickModal(discord.ui.Modal, title="Kick member"):
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=True,
            max_length=1024,
        ),
    )

    # delete history select, same as for BanModal
    delete_history = discord.ui.Label(
        text="Delete message history",
        component=discord.ui.Select(
            placeholder="How much message history to delete?",
            min_values=1,
            max_values=1,
            options=DELETE_HISTORY_OPTIONS,
            required=True,
        ),
    )

    def __init__(self, bot, member: discord.Member):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = self.reason.component.value

        try:
            delete_seconds = DELETE_HISTORY_SECONDS[int(self.delete_history.component.values[0])]
        except (ValueError, IndexError):
            delete_seconds = 0

        # Opened from the user info panel: defer() queues an in-place edit of
        # the panel, edit_original_response() fills it in.
        if interaction.message is not None:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.edit_original_response(
                view=NoticeView("This action can only be used in a guild.")
            )
            return

        member = guild.get_member(self.member.id)
        if member is None:
            await interaction.edit_original_response(
                view=NoticeView("Member is no longer in the server.")
            )
            return

        self.db.actions[member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.KICK,
            reason=reason,
        )

        try:
            if delete_seconds <= 0:
                await member.kick(reason=reason)
            else:
                # guild.ban + unban so the member's recent messages can be
                # mass-deleted -- the kick endpoint can't do that.
                await guild.ban(
                    member,
                    delete_message_seconds=delete_seconds,
                    reason=reason,
                )
                await guild.unban(member)
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView("I do not have permission to kick this member.")
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                view=NoticeView("HTTPException: Kick failed. Try again later.")
            )
            return

        notice = f"{member.mention} has been kicked. Reason: {clip(reason)}"
        info: Optional[MemberInfo] = await self.db.fetch_user_info(member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.edit_original_response(view=NoUserInfoView(notice=notice))
            return

        await interaction.edit_original_response(
            view=UserInfoView(self.bot, info, interaction.user, notice=notice)
        )
