import os
import re
from typing import Optional

import discord

from utils.containers import INFO_ACCENT, NoticeView, avatar_file
from utils.text import render_constants
from .store import get_guide, localize, normalize_lang

# markers inside guide text, both rendered as buttons.
# bname/blabel are set for a btn marker; lbody (the whole "url[:label]") for a link.
MARKER = re.compile(
    r'\[(?:'
    r'btn:\s*"?(?P<bname>[A-Za-z0-9_-]+)"?\s*(?::\s*"?(?P<blabel>[^\]]+?)"?\s*)?'
    r'|'
    r'link:\s*(?P<lbody>[^\]]+?)\s*'
    r')\]'
)

# guide attachment paths are relative to this directory (e.g. "deepfly.txt").
ATTACHMENT_ROOT = "data/assets"


def attachment_file(attachment):
    if not attachment:
        return None, None
    path = os.path.normpath(os.path.join(ATTACHMENT_ROOT, attachment))
    root = os.path.abspath(ATTACHMENT_ROOT)
    if not os.path.abspath(path).startswith(root + os.sep) or not os.path.isfile(path):
        return None, None
    name = os.path.basename(path)
    return discord.File(path, filename=name), name


def split_link(body: str) -> tuple:
    body = body.strip()
    if "://" in body:
        head, sep, tail = body.rpartition(":")
        if sep and "://" in head:
            return head.strip(), (tail.strip() or None)
    return body, None


def is_valid_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def button_targets(text: str) -> list:
    return list(dict.fromkeys(
        m.group("bname").lower() for m in MARKER.finditer(text) if m.group("bname")
    ))


def missing_button_targets(text: str, known_names) -> list:
    known = set(known_names)
    return [name for name in button_targets(text) if name not in known]


def invalid_link_urls(text: str) -> list:
    bad = []
    for m in MARKER.finditer(text):
        if m.group("lbody"):
            url, _ = split_link(m.group("lbody"))
            if not is_valid_url(url):
                bad.append(url)
    return bad


def marker_errors(text: str, known_names) -> list:
    errors = []
    missing = missing_button_targets(text, known_names)
    if missing:
        errors.append("Unknown guide(s) in `[btn:...]`: " + ", ".join(f"`{m}`" for m in missing))
    if bad := invalid_link_urls(text):
        errors.append(
            "Invalid `[link:...]` URL(s) (must start with http:// or https://): "
            + ", ".join(f"`{u}`" for u in bad)
        )
    return errors


def parse_segments(text: str) -> list:
    segments = []
    pos = 0
    for match in MARKER.finditer(text):
        if match.start() > pos:
            segments.append(("text", text[pos:match.start()]))
        if match.group("bname"):
            name = match.group("bname").lower()
            label = (match.group("blabel") or match.group("bname")).strip()
            segments.append(("btn", name, label))
        else:
            url, label = split_link(match.group("lbody"))
            segments.append(("link", url, label))
        pos = match.end()
    if pos < len(text):
        segments.append(("text", text[pos:]))
    return segments


class GuideLinkButton(discord.ui.DynamicItem[discord.ui.Button], template=r"guidelink:(?P<name>[a-z0-9_-]+)"):
    def __init__(self, name: str, label: str):
        self.name = name
        super().__init__(
            discord.ui.Button(
                label=(label or name)[:80],
                custom_id=f"guidelink:{name}",
                style=discord.ButtonStyle.secondary,  # noqa
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        name = match["name"]
        return cls(name, name)

    async def callback(self, interaction: discord.Interaction):
        result = render_guide(self.name, normalize_lang(interaction.locale))
        if result is None:
            await interaction.response.send_message(
                view=NoticeView(f"The `{self.name}` guide is currently unavailable."),
                ephemeral=True,
            )
            return
        view, files = result
        kwargs = {"view": view, "ephemeral": True}
        if files:
            kwargs["files"] = files
        await interaction.response.send_message(**kwargs)


def render_guide(name: str, lang: str, fallback: bool = True) -> Optional[tuple]:
    """Build the sendable view for one guide in the given language"""
    guide = get_guide(name)
    if not guide:
        return None
    text = localize(guide.get("text", {}), lang, fallback=fallback)
    if text is None:
        return None

    text = render_constants(text)
    is_guide_style = guide.get("style") != "notice"
    attachment, attachment_name = attachment_file(guide.get("attachment"))

    items = []
    pending_buttons = []
    avatar_placed = False

    def flush_buttons():
        # discord allows up to 5 buttons per action row
        for start in range(0, len(pending_buttons), 5):
            items.append(discord.ui.ActionRow(*pending_buttons[start:start + 5]))
        pending_buttons.clear()

    for segment in parse_segments(text):
        if segment[0] == "text":
            chunk = segment[1].strip("\n")
            if not chunk.strip():
                continue
            flush_buttons()
            if is_guide_style and not avatar_placed:
                items.append(
                    discord.ui.Section(chunk, accessory=discord.ui.Thumbnail("attachment://avatar.png"))
                )
                avatar_placed = True
            else:
                items.append(discord.ui.TextDisplay(chunk))
        elif segment[0] == "btn":
            _, btn_name, label = segment
            pending_buttons.append(GuideLinkButton(btn_name, label))
        else:  # link
            _, url, label = segment
            if is_valid_url(url):  # skip malformed URLs rather than fail the send
                pending_buttons.append(
                    discord.ui.Button(
                        label=(label or url)[:80],
                        url=url,
                        style=discord.ButtonStyle.link,  # noqa
                    )
                )
    flush_buttons()

    if attachment_name:
        items.append(discord.ui.File(f"attachment://{attachment_name}"))

    files = []
    if avatar_placed:
        files.append(avatar_file())
    if attachment is not None:
        files.append(attachment)

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=INFO_ACCENT))
    return view, files
