import re
from typing import Optional

import discord
from discord.ui import Button
from discord.ext import commands

from extensions.moderator.manager import MemberInfo
from extensions.moderator.views.buttons.ban import BanButton
from extensions.moderator.views.buttons.kick import KickButton
from extensions.moderator.views.buttons.timeout import TimeoutButton
from extensions.moderator.views.buttons.unban import UnbanButton
from extensions.moderator.views.buttons.untimeout import UntimeoutButton
from extensions.moderator.views.entry import RemoveEntryButton
from utils.checks import is_staff
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info


class ModeratorInfoButtons(discord.ui.View):
    """Buttons on log messages to open the moderation info UI."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

    async def get_target_from_embed(
            self, interaction: discord.Interaction
    ) -> discord.abc.User:
        """Derive the target user from the log embed description."""
        msg = interaction.message
        if not msg.embeds:
            raise RuntimeError("Log message has no embeds")

        embed = msg.embeds[0]
        desc = embed.description or ""

        lines = [line.strip() for line in desc.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Log embed description is empty")

        first_line = lines[0]
        mention_re = re.compile(r"<@!?(\d+)>")
        if match := mention_re.search(first_line):
            return await self.bot.get_or_fetch_member(
                guild=interaction.guild, user_id=match[1]
            )
        else:
            raise RuntimeError(f"No user mention found in line: {first_line!r}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global cooldown + staff check for all children."""
        if retry_after := self.cooldown.update_rate_limit(interaction):  # noqa
            await interaction.response.send_message(
                "Hey! Don't spam the buttons.", ephemeral=True
            )
            return False

        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "You're missing the required Role to do that!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="User Info",
        style=discord.ButtonStyle.green,  # noqa
        custom_id="Moderation:info",
    )
    async def mod_info(self, interaction: discord.Interaction, _: Button):
        user = await self.get_target_from_embed(interaction)
        info: Optional[MemberInfo] = await self.bot.moddb.fetch_user_info(user)

        if not info:
            await interaction.response.send_message(
                embed=NoMemberInfoEmbed(), ephemeral=True
            )
            return

        has_any_entries = bool(
            info.timeout_reasons or info.kick_reasons or info.ban_reasons
        )

        mod_cog = self.bot.get_cog("ModAppCommands")
        if mod_cog is None:
            await interaction.response.send_message(
                "Moderation cog is not loaded.", ephemeral=True
            )
            return

        view = MemberModerationView(
            bot=self.bot,
            info=info,
            can_remove_entries=has_any_entries,
        )

        await interaction.response.send_message(
            embeds=full_info(info),
            view=view,
            ephemeral=True,
        )


class MemberModerationView(discord.ui.View):
    """Ephemeral view attached to the full_info(info) response"""

    def __init__(
            self,
            bot,
            info: MemberInfo,
            *,
            can_remove_entries: bool,
            timeout: Optional[float] = 300,
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.info = info
        self.member = info.member

        # Remove-entry button
        self.add_item(
            RemoveEntryButton(self.bot, self.member, disabled=not can_remove_entries)
        )

        # Ban / Unban
        if info.banned:
            self.add_item(UnbanButton(self.bot, self.member))
        else:
            self.add_item(BanButton(self.bot, self.member))

        # Timeout
        now = discord.utils.utcnow()
        is_timed_out = bool(info.timed_out and info.timed_out > now)
        if is_timed_out:
            self.add_item(UntimeoutButton(self.bot, self.member))
        else:
            self.add_item(TimeoutButton(self.bot, self.member))

        # Kick
        self.add_item(KickButton(self.bot, self.member))
