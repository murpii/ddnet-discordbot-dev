from typing import List, Optional, TYPE_CHECKING

import discord

from extensions.management.moderator.manager import MemberInfo, PendingAction, ModAction
from utils.containers import NoticeView
from utils.misc import DELETE_HISTORY_SECONDS
from utils.text import clip

if TYPE_CHECKING:
    from bot import DDNet

DELETE_HISTORY_OPTIONS: List[discord.SelectOption] = [
    discord.SelectOption(label="Don't delete any messages", value="0"),
    discord.SelectOption(label="Last 1 hour", value="1"),
    discord.SelectOption(label="Last 6 hours", value="2"),
    discord.SelectOption(label="Last 12 hours", value="3"),
]


class BanModal(discord.ui.Modal, title="Ban member"):
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=True,
            max_length=1024,
        ),
    )
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

    def __init__(self, bot: "DDNet", member: discord.abc.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = self.reason.component.value

        try:
            delete_seconds = DELETE_HISTORY_SECONDS[int(self.delete_history.component.values[0])]
        except (ValueError, IndexError):
            delete_seconds = 0

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This action can only be used in a guild.",
                ephemeral=True,
            )
            return

        if interaction.message is not None:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)

        # check if already banned, a single lookup instead of paging through the guild's entire ban list
        try:
            await guild.fetch_ban(self.member)
        except discord.NotFound:
            pass  # not banned, proceed
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView("I do not have permission to view bans.")
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                view=NoticeView("HTTPException: Failed to check if user is banned. Try again later.")
            )
            return
        else:
            await interaction.edit_original_response(
                view=NoticeView(f"{self.member.mention} is already banned.")
            )
            return

        self.db.actions[self.member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.BAN,
            reason=reason,
        )

        try:
            await guild.ban(
                self.member,
                delete_message_seconds=delete_seconds,
                reason=reason,
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView("I do not have permission to ban this user.")
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                view=NoticeView("HTTPException: Ban failed. Try again later.")
            )
            return

        notice = f"{self.member.mention} has been banned. Reason: {clip(reason)}"
        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.edit_original_response(view=NoUserInfoView(notice=notice))
            return

        await interaction.edit_original_response(
            view=UserInfoView(self.bot, info, interaction.user, notice=notice)
        )
