from datetime import timedelta
from typing import List, Optional

import discord

from extensions.management.moderator.manager import MemberInfo, PendingAction, ModAction
from utils.containers import NoticeView
from utils.text import clip

TIMEOUT_DURATION_OPTIONS: List[discord.SelectOption] = [
    discord.SelectOption(label="5 minutes", value="5"),
    discord.SelectOption(label="30 minutes", value="30"),
    discord.SelectOption(label="1 hour", value="60"),
    discord.SelectOption(label="6 hours", value="360"),
    discord.SelectOption(label="1 day", value="1440"),
    discord.SelectOption(label="3 days", value="4320"),
    discord.SelectOption(label="1 week", value="10080"),
]


class TimeoutModal(discord.ui.Modal, title="Timeout member"):
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=True,
            max_length=1024,
        ),
    )
    duration = discord.ui.Label(
        text="Duration",
        component=discord.ui.Select(
            placeholder="Select timeout duration",
            min_values=1,
            max_values=1,
            options=TIMEOUT_DURATION_OPTIONS,
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
            minutes = int(self.duration.component.values[0])
        except ValueError:
            await interaction.response.send_message(
                "Invalid timeout duration.", ephemeral=True
            )
            return

        if interaction.message is not None:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)

        now = discord.utils.utcnow()
        if self.member.timed_out_until and self.member.timed_out_until > now:
            ts = int(self.member.timed_out_until.timestamp())
            await interaction.edit_original_response(
                view=NoticeView(
                    f"{self.member.mention} is already timed out. "
                    f"Will be cleared in <t:{ts}:R>."
                )
            )
            return

        self.db.actions[self.member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.TIMEOUT,
            reason=reason,
        )

        try:
            await self.member.timeout(
                timedelta(minutes=minutes),
                reason=reason,
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView("I do not have permission to timeout this member.")
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                view=NoticeView("HTTPException: Timeout failed. Try again later.")
            )
            return

        notice = (
            f"{self.member.mention} has been timed out for {minutes} minutes. "
            f"Reason: {clip(reason)}"
        )
        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.edit_original_response(view=NoUserInfoView(notice=notice))
            return

        await interaction.edit_original_response(
            view=UserInfoView(self.bot, info, interaction.user, notice=notice)
        )
