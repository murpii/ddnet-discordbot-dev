import discord

from extensions.management.moderator.manager import MemberInfo
from extensions.management.moderator.views.buttons.ban import BanButton
from extensions.management.moderator.views.buttons.kick import KickButton
from extensions.management.moderator.views.buttons.timeout import TimeoutButton
from extensions.management.moderator.views.buttons.unban import UnbanButton
from extensions.management.moderator.views.buttons.untimeout import UntimeoutButton
from extensions.management.moderator.views.containers.manage_entries import (
    ManageEntriesButton,
    entry_menu,
)
from utils.checks import is_staff
from utils.containers import ALERT_ACCENT, INFO_ACCENT, separator
from utils.paginator import Pages, page_nav_row
from utils.text import clip, to_discord_timestamp

ENTRIES_PER_PAGE = 5


def history_columns() -> list:
    return [("timeout", "Timeouts"), ("ban", "Bans"), ("kick", "Kicks")]


def format_entry(reason: str, timestamp, invoked_by: str) -> str:
    # 100 chars per reason should keep even a fully loaded panel safely under the 4000 char budget
    return f"[`{timestamp.strftime('%Y-%m-%d %H:%M')}`] {invoked_by} › {clip(reason, 100)}"


class UserInfoView(discord.ui.LayoutView):
    """The staff "User Info" panel"""

    def __init__(
            self,
            bot,
            info: MemberInfo,
            invoker: discord.abc.User,
            *,
            notice: str = None,
            page_numbers: dict = None,
            menu_step: str = None,
            menu_category: str = None,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.info = info
        self.invoker = invoker
        self.notice = notice
        self.menu_step = menu_step
        self.menu_category = menu_category
        self.pages = self.build_pages(page_numbers or {})

        self.add_item(self.build_container())
        if self.menu_step:
            self.add_item(entry_menu(self))

    def build_pages(self, page_numbers: dict) -> dict:
        pages = {}
        for category in ("timeout", "ban", "kick", "name"):
            column = Pages(self.info.entries(category), per_page=ENTRIES_PER_PAGE)
            column.page = min(page_numbers.get(category, 0), column.total_pages - 1)
            pages[category] = column
        return pages

    def current_pages(self) -> dict:
        return {category: column.page for category, column in self.pages.items()}

    def rebuild(self) -> "UserInfoView":
        """Fresh view of the same data, used by the page buttons"""
        return UserInfoView(
            self.bot, self.info, self.invoker,
            notice=self.notice,
            page_numbers=self.current_pages(),
            menu_step=self.menu_step,
            menu_category=self.menu_category,
        )

    def with_menu(self, step: str, category: str = None) -> "UserInfoView":
        """Same panel with the entry menu opened, advanced, or closed"""
        return UserInfoView(
            self.bot, self.info, self.invoker,
            notice=self.notice,
            page_numbers=self.current_pages(),
            menu_step=step,
            menu_category=category,
        )

    def build_container(self) -> discord.ui.Container:
        member = self.info.member
        items = []

        if self.notice:
            items.extend((discord.ui.TextDisplay(f"**{self.notice}**"), separator()))
        items.append(
            discord.ui.Section(
                f"## ⚔️ User Info: {member.mention}",
                self.profile_text(),
                accessory=discord.ui.Thumbnail(member.display_avatar.url),
            )
        )
        items.extend(self.history_items())
        items.extend(self.nickname_items())
        items.extend(
            (
                separator(),
                discord.ui.TextDisplay(self.controls_note()),
                self.control_row(),
            )
        )
        return discord.ui.Container(*items, accent_colour=INFO_ACCENT)

    def can_ban(self) -> bool:
        return is_staff(self.invoker, roles="discord_mods")

    def controls_note(self) -> str:
        if self.can_ban():
            return "-# Moderation controls"
        return "-# Moderation controls -- ban, unban and kick are Discord Moderator only"

    def profile_text(self) -> str:
        member = self.info.member
        joined_at = getattr(member, "joined_at", None)

        now = discord.utils.utcnow()
        if self.info.timed_out and self.info.timed_out > now:
            timeout_status = f"✅ (ends {to_discord_timestamp(self.info.timed_out, 'R')})"
        else:
            timeout_status = "❌"

        return (
            f"Created: {to_discord_timestamp(member.created_at, 'D')}\n"
            f"Joined: {to_discord_timestamp(joined_at, 'D') if joined_at else 'Unknown'}\n\n"
            f"Banned: {'✅' if self.info.banned else '❌'}\n"
            f"Timed out: {timeout_status}\n"
            f"Banned from Testing: {'✅' if self.info.banned_from_testing else '❌'}"
        )

    def history_items(self) -> list:
        """One block per non-empty history column, each with its own page buttons"""
        items = []
        empty_headings = []

        for category, heading in history_columns():
            column = self.pages[category]
            if not column.items:
                empty_headings.append(heading.lower())
                continue
            items.append(separator())
            items.append(discord.ui.TextDisplay(self.history_text(heading, column)))
            items.extend(self.nav_items(category))

        if empty_headings:
            items.append(separator())
            items.append(
                discord.ui.TextDisplay(f"-# No {' / '.join(empty_headings)} on record.")
            )
        return items

    def nickname_items(self) -> list:
        column = self.pages["name"]
        if not column.items:
            return [
                separator(),
                discord.ui.TextDisplay("### Name history\n-# No previous names recorded."),
            ]

        lines = [f"### Name history: {len(column.items)}"]
        lines.extend(
            f"[`{timestamp.strftime('%Y-%m-%d %H:%M')}`] {clip(name, 80)}"
            for _entry_id, name, timestamp in column.current()
        )
        return [separator(), discord.ui.TextDisplay("\n".join(lines)), *self.nav_items("name")]

    def nav_items(self, category: str) -> list:
        column = self.pages[category]
        if column.total_pages < 2 or self.menu_step:
            return []
        return [page_nav_row(column, self.rebuild)]

    @staticmethod
    def history_text(heading: str, column: Pages) -> str:
        lines = [f"### {heading}: {len(column.items)}"]
        lines.extend(
            format_entry(reason, timestamp, invoked_by)
            for _entry_id, reason, timestamp, invoked_by in column.current()
        )
        return "\n".join(lines)

    def control_row(self) -> discord.ui.ActionRow:
        member = self.info.member
        has_entries = bool(
            self.info.timeout_reasons or self.info.kick_reasons or self.info.ban_reasons
        )
        now = discord.utils.utcnow()
        is_timed_out = bool(self.info.timed_out and self.info.timed_out > now)
        locked = not self.can_ban()

        return discord.ui.ActionRow(
            UnbanButton(self.bot, member, disabled=locked) if self.info.banned
            else BanButton(self.bot, member, disabled=locked),
            UntimeoutButton(self.bot, member) if is_timed_out else TimeoutButton(self.bot, member),
            KickButton(self.bot, member, disabled=locked),
            # disabled while the menu is open, its "Cancel" button closes it
            ManageEntriesButton(disabled=not has_entries or self.menu_step is not None),
        )


class NoUserInfoView(discord.ui.LayoutView):
    """Shown when there is no information about a user in the database"""

    def __init__(self, *, notice: str = None):
        super().__init__(timeout=None)
        text = "No user information found."
        if notice:
            text = f"**{notice}**\n{text}"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_colour=ALERT_ACCENT,
            )
        )
