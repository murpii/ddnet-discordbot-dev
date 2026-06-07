import logging

import discord

from constants import Channels, Roles
from utils.containers import ChannelToolView, NoticeView
from extensions.management.moderator.views.containers.channel_tools import SlowmodeView
from extensions.management.tester.bans import TESTING_CATEGORIES

log = logging.getLogger()

# channels inside CAT_TESTING that are NOT map-testing channels and should be
# left out of the pickers.
EXCLUDED_TESTING_CHANNELS = {
    Channels.TESTING_INFO,
    Channels.TESTER_VOTES,
    Channels.TESTER_META,
    Channels.TESTER_HUB,
    Channels.TESTING_SUBMIT,
}

CATEGORY_CHOICES = [
    ("Testing", Channels.CAT_TESTING),
    ("Waiting", Channels.CAT_WAITING),
    ("Evaluated", Channels.CAT_EVALUATED),
]


def testing_channels_in(guild: discord.Guild, category_id: int) -> list:
    """Map-testing text channels of one testing category, position-ordered, with
    the meta channels (info/votes/meta/hub/submit) removed."""
    category = guild.get_channel(category_id) if guild else None
    if not isinstance(category, discord.CategoryChannel):
        return []
    return [c for c in category.text_channels if c.id not in EXCLUDED_TESTING_CHANNELS]


class TestingCategorySelect(discord.ui.Select):
    """Picks which testing category; re-renders the view so the channel select
    below lists that category's channels."""

    def __init__(self, selected: int | None):
        super().__init__(
            placeholder="Pick a category",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=label, value=str(cid), default=(selected == cid))
                for label, cid in CATEGORY_CHOICES
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        rebuilt = type(self.view)(self.view.guild, category=int(self.values[0]))
        await interaction.response.edit_message(view=rebuilt)


SELECT_LIMIT = 25

class TestingChannelSelect(discord.ui.Select):
    """One page of channels (<=25); stores the pick on the view as target_channel."""

    def __init__(self, channels: list, placeholder: str = "Pick a channel"):
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=f"#{c.name}"[:100], value=str(c.id)) for c in channels],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.target_channel = interaction.guild.get_channel(int(self.values[0]))
        await interaction.response.defer()


def disabled_select(placeholder: str) -> discord.ui.Select:
    return discord.ui.Select(
        placeholder=placeholder,
        options=[discord.SelectOption(label="(none)", value="0")],
        disabled=True,
    )


class TestingChannelPicker:
    def channel_rows(self) -> list:
        rows = [discord.ui.ActionRow(TestingCategorySelect(self.category))]
        if not self.category:
            rows.append(discord.ui.ActionRow(disabled_select("Pick a category first")))
            return rows

        channels = testing_channels_in(self.guild, self.category)
        if not channels:
            rows.append(discord.ui.ActionRow(disabled_select("No channels in this category")))
            return rows

        pages = [channels[i:i + SELECT_LIMIT] for i in range(0, len(channels), SELECT_LIMIT)]
        for index, page in enumerate(pages):
            if len(pages) > 1:
                start = index * SELECT_LIMIT + 1
                placeholder = f"Pick a channel ({start}-{start + len(page) - 1})"
            else:
                placeholder = "Pick a channel"
            rows.append(discord.ui.ActionRow(TestingChannelSelect(page, placeholder)))
        return rows


class TestingChannelCheck:
    async def require_channel(self, interaction: discord.Interaction):
        channel = await super().require_channel(interaction)
        if channel is not None and channel.category_id not in TESTING_CATEGORIES:
            await interaction.response.send_message(
                view=NoticeView(f"{channel.mention} is not a testing channel."),
                ephemeral=True,
            )
            return None
        return channel


class TestingSlowmodeView(TestingChannelCheck, TestingChannelPicker, SlowmodeView):
    instructions = "Pick a category, then a testing channel and a delay, then press Apply."

    def __init__(self, guild: discord.Guild, *, category: int | None = None):
        self.guild = guild
        self.category = category
        super().__init__()


class ReadOnlyButton(discord.ui.Button):
    def __init__(self, *, read_only: bool):
        style = discord.ButtonStyle.danger if read_only else discord.ButtonStyle.success
        super().__init__(label="Make read-only" if read_only else "Allow writing", style=style)  # noqa
        self.read_only = read_only

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await self.view.require_channel(interaction)
        if channel is None:
            return

        roles = [interaction.guild.default_role]
        if testing_role := interaction.guild.get_role(Roles.TESTING):
            roles.append(testing_role)

        word = "read-only" if self.read_only else "writable again"
        try:
            for role in roles:
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = False if self.read_only else None  # None = inherit
                await channel.set_permissions(
                    role,
                    overwrite=overwrite,
                    reason=f"Made {word} by {interaction.user} via tester hub",
                )
        except discord.Forbidden:
            await interaction.response.edit_message(
                view=NoticeView(f"I am not allowed to edit {channel.mention}.")
            )
            return

        log.info("TesterHub: %s made #%s %s", interaction.user, channel, word)
        await interaction.response.edit_message(
            view=NoticeView(f"{channel.mention} is now {word}.")
        )


class TestingReadOnlyView(TestingChannelCheck, TestingChannelPicker, ChannelToolView):
    title = "Read-only (testing channels)"
    instructions = (
        "Pick a category, then a testing channel. Read-only denies sending "
        "messages for @everyone and the Testing role; Allow writing resets both "
        "permissions to inherit again."
    )

    def __init__(self, guild: discord.Guild, *, category: int | None = None):
        self.guild = guild
        self.category = category
        super().__init__()

    def extra_rows(self) -> list:
        return [discord.ui.ActionRow(ReadOnlyButton(read_only=True), ReadOnlyButton(read_only=False))]
