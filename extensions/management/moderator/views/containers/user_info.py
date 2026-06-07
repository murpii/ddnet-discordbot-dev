import discord

from utils.paginator import Pages, page_nav_row
from utils.text import to_discord_timestamp
from extensions.management.moderator.manager import MemberInfo
from utils.containers import INFO_ACCENT, ALERT_ACCENT, separator
from utils.text import clip
from extensions.management.moderator.views.containers.remove_entry import RemoveEntryButton, removal_container
from extensions.management.moderator.views.buttons.ban import BanButton
from extensions.management.moderator.views.buttons.kick import KickButton
from extensions.management.moderator.views.buttons.timeout import TimeoutButton
from extensions.management.moderator.views.buttons.unban import UnbanButton
from extensions.management.moderator.views.buttons.untimeout import UntimeoutButton

MAX_ENTRIES_PER_CATEGORY = 5
NICKNAMES_PER_PAGE = 5


def format_entry(reason: str, timestamp, invoked_by: str) -> str:
    # 100 chars per reason should keep even a fully loaded panel safely under the 4000 char budget
    return f"[`{timestamp.strftime('%Y-%m-%d %H:%M')}`] {invoked_by} › {clip(reason, 100)}"


class UserInfoView(discord.ui.LayoutView):
    """The staff "User Info" panel"""

    def __init__(
            self,
            bot,
            info: MemberInfo,
            *,
            notice: str = None,
            pages: Pages = None,
            removal_step: str = None,
            removal_category: str = None,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.info = info
        self.notice = notice
        self.removal_step = removal_step
        self.removal_category = removal_category
        self.pages = pages or Pages(
            sorted(info.nicknames, key=lambda entry: entry[1], reverse=True),  # newest first
            per_page=NICKNAMES_PER_PAGE,
        )

        self.add_item(self.build_container())
        if self.removal_step:
            self.add_item(removal_container(self))

    def rebuild(self) -> "UserInfoView":
        """Fresh view of the same data, used by the page buttons"""
        return UserInfoView(
            self.bot, self.info,
            notice=self.notice,
            pages=self.pages,
            removal_step=self.removal_step,
            removal_category=self.removal_category,
        )

    def with_removal(self, step: str, category: str = None) -> "UserInfoView":
        """Same panel with the removal menu opened, advanced, or closed"""
        return UserInfoView(
            self.bot, self.info,
            notice=self.notice,
            pages=self.pages,
            removal_step=step,
            removal_category=category,
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
        items.extend(
            (
                separator(),
                discord.ui.TextDisplay(self.history_text()),
                separator(),
                discord.ui.TextDisplay(self.nickname_text()),
            )
        )
        if self.pages.total_pages > 1:
            items.append(page_nav_row(self.pages, self.rebuild))
        items.extend(
            (
                separator(),
                discord.ui.TextDisplay("-# Moderation controls"),
                self.control_row(),
            )
        )
        return discord.ui.Container(*items, accent_colour=INFO_ACCENT)

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

    def history_text(self) -> str:
        """Timeouts/bans/kicks with per entry invoker, newest first"""
        blocks = []
        empty_labels = []

        categories = (
            ("Timeouts", self.info.timeout_reasons),
            ("Bans", self.info.ban_reasons),
            ("Kicks", self.info.kick_reasons),
        )
        for label, entries in categories:
            if not entries:
                empty_labels.append(label.lower())
                continue

            newest_first = sorted(entries, key=lambda entry: entry[1], reverse=True)
            lines = [f"### {label}: {len(entries)}"]
            lines.extend(
                format_entry(reason, timestamp, invoked_by)
                for reason, timestamp, invoked_by in newest_first[
                    :MAX_ENTRIES_PER_CATEGORY
                ]
            )
            if len(entries) > MAX_ENTRIES_PER_CATEGORY:
                lines.append(f"-# ... and {len(entries) - MAX_ENTRIES_PER_CATEGORY} older entries")
            blocks.append("\n".join(lines))

        if empty_labels:
            blocks.append(f"-# No {' / '.join(empty_labels)} on record.")

        return "\n".join(blocks)

    def nickname_text(self) -> str:
        if not self.pages.items:
            return "### Name history\n-# No previous names recorded."

        lines = [f"### Name history: {len(self.pages.items)}"]
        lines.extend(
            f"[`{timestamp.strftime('%Y-%m-%d %H:%M')}`] {clip(name, 80)}"
            for name, timestamp in self.pages.current()
        )
        return "\n".join(lines)

    def control_row(self) -> discord.ui.ActionRow:
        member = self.info.member
        has_entries = bool(
            self.info.timeout_reasons or self.info.kick_reasons or self.info.ban_reasons
        )
        now = discord.utils.utcnow()
        is_timed_out = bool(self.info.timed_out and self.info.timed_out > now)

        return discord.ui.ActionRow(
            UnbanButton(self.bot, member) if self.info.banned else BanButton(self.bot, member),
            UntimeoutButton(self.bot, member) if is_timed_out else TimeoutButton(self.bot, member),
            KickButton(self.bot, member),
            # disabled while the menu is open, its "Cancel" button closes it
            RemoveEntryButton(disabled=not has_entries or self.removal_step is not None),
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
