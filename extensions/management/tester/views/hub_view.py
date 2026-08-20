import logging

import discord
from discord.ext import commands

from constants import Channels
from utils.containers import INFO_ACCENT, NoticeView, separator
from extensions.management.hub import HubButton, staff_guard
from extensions.management.tester.views.bans import (
    TestingBanView,
    TestingUnbanView,
    banned_list_view,
    changelog_view,
)
from extensions.management.tester.views.channel_tools import TestingReadOnlyView, TestingSlowmodeView
from extensions.management.tester.views.promote import PROMOTION_ROLES, PromoteStartView

log = logging.getLogger()


class TestingBanButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Ban", custom_id="TesterHub:ban",
            style=discord.ButtonStyle.danger,  # noqa
            roles="testers",
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=TestingBanView(), ephemeral=True)


class TestingUnbanButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Unban", custom_id="TesterHub:unban", roles="testers")

    async def run(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("TesterBans")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The testing ban system is not loaded."), ephemeral=True
            )
            return
        if not cog.active:
            await interaction.response.send_message(
                view=NoticeView("Nobody is banned from testing."), ephemeral=True
            )
            return
        await interaction.response.send_message(view=TestingUnbanView(cog), ephemeral=True)


class BannedListButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Who is banned", custom_id="TesterHub:banned-list", roles="testers")

    async def run(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("TesterBans")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The testing ban system is not loaded."), ephemeral=True
            )
            return
        await interaction.response.send_message(view=banned_list_view(cog), ephemeral=True)


class BanChangelogButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Changelog", custom_id="TesterHub:ban-log", roles="testers")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.edit_original_response(view=await changelog_view(self.bot))


class TestingSlowmodeButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Slowmode", custom_id="TesterHub:slowmode", roles="testers")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=TestingSlowmodeView(interaction.guild), ephemeral=True)


class TestingReadOnlyButton(HubButton):
    def __init__(self, bot):
        super().__init__(bot, label="Read-only", custom_id="TesterHub:read-only", roles="testers")

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=TestingReadOnlyView(interaction.guild), ephemeral=True)


class SuggestPromotionButton(HubButton):
    def __init__(self, bot):
        super().__init__(
            bot, label="Suggest promotion", custom_id="TesterHub:promote",
            style=discord.ButtonStyle.primary,  # noqa
        )

    async def run(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=PromoteStartView(interaction.user), ephemeral=True
        )


class TesterHubView(discord.ui.LayoutView):
    """The persistent tester hub message. Every flow it opens is
    ephemeral, so the hub message itself never changes."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("# Tester Commands Hub"),
                separator(),
                discord.ui.TextDisplay(
                    "## Testing bans\n"
                    "Ban disruptive people from the testing area. Every action "
                    "lands in the changelog."
                ),
                discord.ui.ActionRow(
                    TestingBanButton(bot), TestingUnbanButton(bot),
                    BannedListButton(bot), BanChangelogButton(bot),
                ),
                separator(),
                discord.ui.TextDisplay(
                    "## Channel tools\n"
                    "Slowmode and read-only, restricted to channels of the "
                    "testing categories. Read-only also covers people with "
                    "the Testing role."
                ),
                discord.ui.ActionRow(TestingSlowmodeButton(bot), TestingReadOnlyButton(bot)),
                separator(),
                discord.ui.TextDisplay(
                    "## Promotions\n"
                    "Suggest someone for the Trial Tester or Tester role.\n"
                    "This opens a private vote thread where every Tester can vote.\n"
                    "After 3 days, if the vote is in favour, the promotion can be carried out from the thread."
                ),
                discord.ui.ActionRow(SuggestPromotionButton(bot)),
                accent_colour=INFO_ACCENT,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction, roles=PROMOTION_ROLES)
