import logging

import discord

from utils.containers import INFO_ACCENT, NoticeView, OptionSelect, PagedLines, separator
from utils.text import clip
from extensions.management.tester import queries

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger()


def banned_list_view(cog) -> PagedLines:
    """Paged overview of everyone currently banned from testing"""
    bans = sorted(cog.active.values(), key=lambda ban: ban.timestamp, reverse=True)
    lines = [
                f"<@{ban.user_id}> -- {clip(ban.reason, 80)} "
                f"-- by <@{ban.banned_by}> <t:{ban.timestamp}:R>"
                for ban in bans
            ] or ["-# Nobody is banned from testing."]
    return PagedLines(f"Banned from testing: {len(bans)}", lines)


async def changelog_view(bot: "DDNet") -> PagedLines:
    """Paged changelog of the latest 200 ban and unban actions"""
    rows = await bot.fetch(queries.SELECT_BAN_LOG, fetchall=True)

    lines = []
    for user_id, action, reason, invoked_by, timestamp in rows:
        when = f"<t:{int(timestamp)}:R>"
        if action == "testing_ban":
            lines.append(
                f"`ban` <@{user_id}> by <@{invoked_by}> {when} -- {clip(reason or 'No reason', 70)}"
            )
        else:
            lines.append(f"`unban` <@{user_id}> by <@{invoked_by}> {when}")

    if not lines:
        lines = ["-# No testing ban actions recorded yet."]
    return PagedLines("Testing ban changelog", lines)


class BanTargetSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Pick a user", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.target = self.values[0]
        await interaction.response.defer()


class BanReasonModal(discord.ui.Modal, title="Ban from testing"):
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=200,
        ),
    )

    def __init__(self, target):
        super().__init__(timeout=300)
        self.target = target

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("TesterBans")  # noqa
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The testing ban system is not loaded."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await cog.ban(
            self.target,
            banned_by=interaction.user,
            reason=self.reason.component.value.strip(),
        )
        await interaction.edit_original_response(view=NoticeView(result))


class StartBanButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Ban...", style=discord.ButtonStyle.danger)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view.target is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a user first."), ephemeral=True
            )
            return
        await interaction.response.send_modal(BanReasonModal(self.view.target))


class TestingBanView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=300)
        self.target = None

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Ban from testing\n"
                    "Pick a user, then press Ban and give a reason. The ban "
                    "hides all testing channels, removes the Testing role and "
                    "survives leaving and rejoining the server."
                ),
                separator(),
                discord.ui.ActionRow(BanTargetSelect()),
                discord.ui.ActionRow(StartBanButton()),
                accent_colour=INFO_ACCENT,
            )
        )


# ----------------------------------------------------------------------
# Unban flow: pick one of the currently banned users
# ----------------------------------------------------------------------

class UnbanButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Unban", style=discord.ButtonStyle.success)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view.user_id is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a banned user first."), ephemeral=True
            )
            return

        cog = interaction.client.get_cog("TesterBans")
        if cog is None:
            await interaction.response.send_message(
                view=NoticeView("The testing ban system is not loaded."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await cog.unban(int(self.view.user_id), unbanned_by=interaction.user)
        await interaction.edit_original_response(view=NoticeView(result))


class TestingUnbanView(discord.ui.LayoutView):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.user_id = None

        bans = sorted(cog.active.values(), key=lambda ban: ban.timestamp, reverse=True)
        options = [
            discord.SelectOption(
                label=ban.user_name,
                value=str(ban.user_id),
                description=clip(ban.reason, 90),
            )
            for ban in bans[:25]
        ]

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Lift a testing ban\n"
                    "Pick a banned user, then press Unban. Their testing "
                    "channel overwrites are removed again."
                ),
                separator(),
                discord.ui.ActionRow(OptionSelect("Pick a banned user", "user_id", options)),
                discord.ui.ActionRow(UnbanButton()),
                accent_colour=INFO_ACCENT,
            )
        )
