from typing import List, Optional

import discord

from utils.paginator import Pages, page_nav_row
from utils.text import clip

# Accent colours shared across the staff containers
INFO_ACCENT = 3619648  # similar to embeds
ALERT_ACCENT = discord.Colour.red().value  # log entries and alerts
AVATAR_PATH = "data/assets/avatar.png"


def separator() -> discord.ui.Separator:
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True)  # noqa


def avatar_file() -> discord.File:
    """
    The bot avatar. Send it together with a GuideView, whose thumbnail
    references it as attachment://avatar.png
    """
    return discord.File(AVATAR_PATH, filename="avatar.png")


class GuideView(discord.ui.LayoutView):
    """
    The standard helper-guide container: markdown text with the bot avatar
    as thumbnail. Send it together with avatar_file().
    """

    def __init__(self, text: str, *, accent: int = INFO_ACCENT, attachment: Optional[str] = None):
        super().__init__(timeout=None)
        items = [
            discord.ui.Section(
                text,
                accessory=discord.ui.Thumbnail("attachment://avatar.png"),
            )
        ]
        if attachment:
            items.append(discord.ui.File(f"attachment://{attachment}"))
        self.add_item(discord.ui.Container(*items, accent_colour=accent))


class NoticeView(discord.ui.LayoutView):
    """
    Bare-bones container with a single block of text. Used for error
    messages and short statuses where a full panel is not applicable.
    """

    def __init__(self, text: str, *, accent: int = INFO_ACCENT, attachment: Optional[str] = None):
        super().__init__(timeout=None)
        items = [discord.ui.TextDisplay(text)]
        if attachment:
            items.append(discord.ui.File(f"attachment://{attachment}"))
        self.add_item(discord.ui.Container(*items, accent_colour=accent))


class PagedLines(discord.ui.LayoutView):
    """Generic paged list container: a title plus lines, with a Previous/Next
    row appearing automatically when there is more than one page"""

    def __init__(self, title: str, lines: List[str], *, pages: Pages = None, per_page: int = 10):
        super().__init__(timeout=300)
        self.title = title
        self.lines = lines
        self.pages = pages or Pages(lines, per_page=per_page)

        items = [discord.ui.TextDisplay("\n".join([f"## {title}", *self.pages.current()]))]
        if self.pages.total_pages > 1:
            items.append(separator())
            items.append(page_nav_row(self.pages, self.rebuild))

        self.add_item(discord.ui.Container(*items, accent_colour=INFO_ACCENT))

    def rebuild(self) -> "PagedLines":
        return PagedLines(self.title, self.lines, pages=self.pages)


def paged_pairs_view(title: str, pairs, *, empty_note: str, per_page: int = 10) -> PagedLines:
    """Paged "`key` › value" overview for key/value tables, e.g. the word
    blacklist (trigger -> response) and the auto-responses. One shared
    builder instead of one list view class per table."""
    pairs = sorted(pairs)
    lines = [f"`{clip(key, 60)}` › {clip(value, 80)}" for key, value in pairs]
    if not lines:
        lines = [f"-# {empty_note}"]
    return PagedLines(f"{title}: {len(pairs)}", lines, per_page=per_page)


class TargetChannelSelect(discord.ui.ChannelSelect):
    """
    Channel picker shared by the channel tools. Stores the picked text
    channel on the parent view as `target_channel`.
    """

    def __init__(self):
        super().__init__(
            placeholder="Pick a channel",
            channel_types=[discord.ChannelType.text],  # noqa
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        picked = self.values[0]
        self.view.target_channel = picked.resolve() or interaction.guild.get_channel(picked.id)
        await interaction.response.defer()  # selection itself changes nothing visible


class OptionSelect(discord.ui.Select):
    """Dropdown that just remembers the picked value on the parent view."""

    def __init__(self, placeholder: str, attr: str, options: List[discord.SelectOption]):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.attr = attr

    async def callback(self, interaction: discord.Interaction) -> None:
        setattr(self.view, self.attr, self.values[0])
        await interaction.response.defer()


class ChannelToolView(discord.ui.LayoutView):
    """Base for ephemeral channel tools: a short instruction, a channel
    picker, and whatever extra rows the subclass adds."""

    title = "Channel tool"
    instructions = ""

    def __init__(self):
        super().__init__(timeout=180)
        self.target_channel: Optional[discord.TextChannel] = None

        items = [
            discord.ui.TextDisplay(f"## {self.title}\n{self.instructions}"),
            separator(),
            *self.channel_rows(),
            *self.extra_rows(),
        ]
        self.add_item(discord.ui.Container(*items, accent_colour=INFO_ACCENT))

    def channel_rows(self) -> list:
        return [discord.ui.ActionRow(TargetChannelSelect())]

    def extra_rows(self) -> list:
        return []

    async def require_channel(self, interaction: discord.Interaction) -> Optional[discord.TextChannel]:
        if self.target_channel is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a channel first."), ephemeral=True
            )
        return self.target_channel
