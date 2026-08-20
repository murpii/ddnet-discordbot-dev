import re
from typing import List, Optional

import discord
from discord.components import Container as ContainerComponent, TextDisplay as TextDisplayComponent

from utils.paginator import Pages, page_nav_row
from utils.text import clip

INFO_ACCENT = 3619648  # similar to default discord embeds
ALERT_ACCENT = discord.Colour.red().value
EMBED_BLOCK = re.compile(
    r"^[ \t]*\[embed(?::[ \t]*#?(?P<accent>[0-9A-Fa-f]{6}))?\][ \t]*\n"
    r"(?P<body>.*?)"
    r"\n[ \t]*\[/embed\][ \t]*$",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def has_embed_blocks(text: str) -> bool:
    return EMBED_BLOCK.search(text) is not None


def parse_embed_segments(text: str) -> list:
    segments = []
    pos = 0
    for match in EMBED_BLOCK.finditer(text):
        if match.start() > pos:
            segments.append(("text", text[pos:match.start()], None))
        accent = int(match["accent"], 16) if match["accent"] else None
        segments.append(("embed", match["body"], accent))
        pos = match.end()
    if pos < len(text):
        segments.append(("text", text[pos:], None))
    return segments


def markup_view(text: str) -> discord.ui.LayoutView:
    items = []
    for kind, chunk, accent in parse_embed_segments(text):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        if kind == "embed":
            items.append(discord.ui.Container(
                discord.ui.TextDisplay(chunk),
                accent_colour=INFO_ACCENT if accent is None else accent,
            ))
        else:
            items.append(discord.ui.TextDisplay(chunk))
    if not items:
        items = [discord.ui.TextDisplay(text.strip() or "...")]

    view = discord.ui.LayoutView(timeout=None)
    for item in items:
        view.add_item(item)
    return view


def markup_kwargs(text: str) -> dict:
    if has_embed_blocks(text):
        return {"view": markup_view(text)}
    return {"content": text}


def message_markup(message: discord.Message) -> Optional[str]:
    if not message.flags.components_v2:
        return None
    parts = []
    for component in message.components:
        if isinstance(component, TextDisplayComponent):
            parts.append(component.content)
        elif isinstance(component, ContainerComponent):
            texts = []
            for child in component.children:
                if not isinstance(child, TextDisplayComponent):
                    return None
                texts.append(child.content)
            colour = component.accent_colour
            accent = f":#{colour.value:06X}" if colour and colour.value != INFO_ACCENT else ""
            parts.append(f"[embed{accent}]\n" + "\n".join(texts) + "\n[/embed]")
        else:
            return None
    return "\n".join(parts) if parts else None


def separator() -> discord.ui.Separator:
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True)  # noqa


def avatar_file() -> discord.File:
    return discord.File("data/assets/avatar.png", filename="avatar.png")


class GuideView(discord.ui.LayoutView):
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
    def __init__(self, text: str, *, accent: int = INFO_ACCENT, attachment: Optional[str] = None):
        super().__init__(timeout=None)
        items = [discord.ui.TextDisplay(text)]
        if attachment:
            items.append(discord.ui.File(f"attachment://{attachment}"))
        self.add_item(discord.ui.Container(*items, accent_colour=accent))


class PagedLines(discord.ui.LayoutView):
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
    pairs = sorted(pairs)
    lines = [f"`{clip(key, 60)}` › {clip(value, 80)}" for key, value in pairs]
    if not lines:
        lines = [f"-# {empty_note}"]
    return PagedLines(f"{title}: {len(pairs)}", lines, per_page=per_page)


class TargetChannelSelect(discord.ui.ChannelSelect):
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
    def __init__(self, placeholder: str, attr: str, options: List[discord.SelectOption]):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.attr = attr

    async def callback(self, interaction: discord.Interaction) -> None:
        setattr(self.view, self.attr, self.values[0])
        await interaction.response.defer()


class ChannelToolView(discord.ui.LayoutView):
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
