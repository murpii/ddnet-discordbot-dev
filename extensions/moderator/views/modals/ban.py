from typing import Optional, List

import discord

from extensions.moderator.manager import MemberInfo, PendingAction, ModAction
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info

seconds_list = [0, 3600, 21600, 43200, 86400, 259200, 604800]

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

    def __init__(self, bot, member: discord.abc.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = self.reason.component.value
        choice_raw = self.delete_history.component.values[0]

        try:
            choice_index = int(choice_raw)
        except ValueError:
            await interaction.response.send_message(
                "Invalid delete history choice.", ephemeral=True
            )
            return

        try:
            delete_seconds = seconds_list[choice_index]
        except Exception:
            delete_seconds = 0

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This action can only be used in a guild.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # check if already banned
        try:
            is_banned = False
            async for ban_entry in guild.bans():
                if ban_entry.user.id == self.member.id:
                    is_banned = True
                    break

            if is_banned:
                await interaction.edit_original_response(
                    content=f"{self.member.mention} is already banned.",
                    embeds=[],
                    view=None,
                )
                return
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="I do not have permission to view bans.",
                embeds=[],
                view=None,
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                content="HTTPException: Failed to check if user is banned. Try again later.",
                embeds=[],
                view=None,
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
                content="I do not have permission to ban this user.",
                embeds=[],
                view=None,
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                content="HTTPException: Ban failed. Try again later.",
                embeds=[],
                view=None,
            )
            return

        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)
        if not info:
            await interaction.edit_original_response(
                content=f"User {self.member.mention} has been banned.",
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
            content=f"User {self.member.mention} has been banned.",
            embeds=updated_embeds,
            view=view,
        )
