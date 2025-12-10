from typing import Optional

import discord

from extensions.moderator.commands.app_commands import seconds_list
from extensions.moderator.manager import MemberInfo, PendingAction, ModAction
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info
from extensions.moderator.views.modals.ban import DELETE_HISTORY_OPTIONS


class KickModal(discord.ui.Modal, title="Kick member"):
    """A modal dialog for kicking a member from the server. Allows moderators to specify a reason and optionally delete message history.

    Args:
        bot: The Discord bot instance.
        member: The member to be kicked.
    """

    # Reason input
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1024,
        ),
    )

    # Delete history select, same as for BanModal
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
        choice_raw = self.delete_history.component.values[0]

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.edit_original_response(
                content="This action can only be used in a guild.",
                embeds=[],
                view=None,
            )
            return

        member = guild.get_member(self.member.id)
        if member is None:
            await interaction.edit_original_response(
                content="Member is no longer in the server.",
                embeds=[],
                view=None,
            )
            return

        try:
            delete_index = int(choice_raw)
        except ValueError:
            await interaction.edit_original_response(
                content="Invalid delete history choice.",
                embeds=[],
                view=None,
            )
            return

        try:
            delete_seconds = seconds_list[delete_index]
        except Exception:
            delete_seconds = 0

        self.db.actions[member.id] = PendingAction(
            moderator=interaction.user,
            action=ModAction.KICK,
            reason=reason,
        )

        if delete_seconds <= 0:
            try:
                await member.kick(reason=reason)
            except discord.Forbidden:
                await interaction.edit_original_response(
                    content="I do not have permission to kick this member.",
                    embeds=[],
                    view=None,
                )
                return
            except discord.HTTPException:
                await interaction.edit_original_response(
                    content="HTTPException: Kick failed. Try again later.",
                    embeds=[],
                    view=None,
                )
                return

            info: Optional[MemberInfo] = await self.db.fetch_user_info(member)
            if not info:
                await interaction.edit_original_response(
                    content=f"User {member.mention} has been kicked. Reason: {reason}",
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
                content=f"User {member.mention} has been kicked. Reason: {reason}",
                embeds=updated_embeds,
                view=view,
            )
            return

        try:
            await guild.ban(
                member,
                delete_message_seconds=delete_seconds,
                reason=reason,
            )
            await guild.unban(member)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="I do not have permission to kick this member (ban/unban failed).",
                embeds=[],
                view=None,
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                content="HTTPException: Kick failed. Try again later.",
                embeds=[],
                view=None,
            )
            return

        info: Optional[MemberInfo] = await self.db.fetch_user_info(member)
        if not info:
            await interaction.edit_original_response(
                content=(
                    f"User {member.mention} has been kicked. "
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
            content=f"User {member.mention} has been kicked. Reason: {reason}",
            embeds=updated_embeds,
            view=view,
        )
