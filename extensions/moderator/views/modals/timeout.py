from datetime import timedelta
from typing import Optional, List

import discord

from extensions.moderator.manager import MemberInfo, PendingAction, ModAction
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info

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
        duration_raw = self.duration.component.values[0]

        try:
            minutes = int(duration_raw)
        except ValueError:
            await interaction.response.send_message(
                "Invalid timeout duration.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        now = discord.utils.utcnow()
        if self.member.timed_out_until and self.member.timed_out_until > now:
            ts = int(self.member.timed_out_until.timestamp())
            await interaction.edit_original_response(
                content=(
                    f"{self.member.mention} is already timed out. "
                    f"Will be cleared in <t:{ts}:R>."
                ),
                embeds=[],
                view=None,
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
                content="I do not have permission to timeout this member.",
                embeds=[],
                view=None,
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                content="HTTPException: Timeout failed. Try again later.",
                embeds=[],
                view=None,
            )
            return

        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)
        if not info:
            await interaction.edit_original_response(
                content=(
                    f"User {self.member.mention} has been timed out for {minutes} minutes. "
                    f"Reason: {reason}"
                ),
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

        await interaction.edit_original_response(
            content=(
                f"User {self.member.mention} has been timed out for {minutes} minutes. "
                f"Reason: {reason}"
            ),
            embeds=updated_embeds,
            view=view,
        )
