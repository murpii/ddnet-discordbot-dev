from datetime import datetime
from typing import List, Optional, Tuple

import discord

from utils.containers import INFO_ACCENT, separator
from utils.text import clip

Entry = Tuple[int, str, datetime, str]
OPTIONS_PER_SELECT = 25


def entry_menu(panel) -> discord.ui.Container:
    if panel.menu_step == "select":
        entries = panel.info.entries(panel.menu_category)
        note = f"**{panel.menu_category.capitalize()} entries for {panel.info.member.mention}**"
        if len(entries) > OPTIONS_PER_SELECT:
            note += f"\n-# Showing the {OPTIONS_PER_SELECT} newest of {len(entries)}."
        return discord.ui.Container(
            discord.ui.TextDisplay(note),
            discord.ui.ActionRow(RemoveSelect(panel.menu_category, entries)),
            discord.ui.ActionRow(EditSelect(panel.menu_category, entries)),
            discord.ui.ActionRow(CancelButton()),
            accent_colour=INFO_ACCENT,
        )

    return discord.ui.Container(
        discord.ui.TextDisplay(
            f"**Choose which entries to manage for {panel.info.member.mention}:**"
        ),
        separator(),
        discord.ui.ActionRow(
            CategoryButton("Timeouts", "timeout", disabled=not panel.info.timeout_reasons),
            CategoryButton("Bans", "ban", disabled=not panel.info.ban_reasons),
            CategoryButton("Kicks", "kick", disabled=not panel.info.kick_reasons),
            CancelButton(),
        ),
        accent_colour=INFO_ACCENT,
    )


def entry_options(entries: List[Entry]) -> List[discord.SelectOption]:
    """One option per entry, valued by its row id so an action hits exactly that row"""
    return [
        discord.SelectOption(
            label=f"{position}. {timestamp.strftime('%Y-%m-%d %H:%M')} by {clip(invoked_by or '?', 40)}",
            description=clip(reason or "no reason given", 90),
            value=str(entry_id),
        )
        for position, (entry_id, reason, timestamp, invoked_by)
        in enumerate(entries[:OPTIONS_PER_SELECT], start=1)
    ]


def picked_ids(values: List[str]) -> List[int]:
    """Row ids of the picked options, skipping anything that is not a number"""
    ids = []
    for value in values:
        try:
            ids.append(int(value))
        except ValueError:
            continue
    return ids


def find_entry(entries: List[Entry], value: str) -> Optional[Entry]:
    for entry in entries:
        if str(entry[0]) == value:
            return entry
    return None


async def reopened_panel(panel, *, notice: str):
    """The user info panel redrawn from fresh data, with the menu closed again"""
    info = await panel.bot.moddb.fetch_user_info(panel.info.member)

    from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
    if not info:
        return NoUserInfoView(notice=notice)

    return UserInfoView(
        panel.bot, info, panel.invoker,
        notice=notice,
        page_numbers=panel.current_pages(),
    )


class ManageEntriesButton(discord.ui.Button):
    def __init__(self, *, disabled: bool = False):
        super().__init__(
            label="Edit / Remove Entry",
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view  # the UserInfoView this button sits in
        await interaction.response.edit_message(view=panel.with_menu("category"))


class CategoryButton(discord.ui.Button):
    def __init__(self, label: str, category: str, *, disabled: bool = False):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )
        self.category = category  # "timeout" | "kick" | "ban"

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        await interaction.response.edit_message(
            view=panel.with_menu("select", self.category)
        )


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        await interaction.response.edit_message(view=panel.with_menu(None))


class RemoveSelect(discord.ui.Select):
    def __init__(self, category: str, entries: List[Entry]):
        self.category = category
        self.entries = entries

        options = entry_options(entries)
        super().__init__(
            placeholder=f"Remove one or more {category} entries",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        db = panel.bot.moddb

        removed = 0
        for entry_id in picked_ids(self.values):
            removed += await db.remove_user_entry(panel.info.member, self.category, entry_id)

        if not removed:
            await interaction.response.send_message(
                "Nothing was removed, those entries may already be gone.", ephemeral=True
            )
            return

        notice = f"Removed {removed} {self.category} entr{'y' if removed == 1 else 'ies'}."
        await interaction.response.edit_message(view=await reopened_panel(panel, notice=notice))


class EditSelect(discord.ui.Select):
    def __init__(self, category: str, entries: List[Entry]):
        self.category = category
        self.entries = entries

        super().__init__(
            placeholder=f"Edit the reason of a {category} entry",
            min_values=1,
            max_values=1,
            options=entry_options(entries),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        entry = find_entry(self.entries, self.values[0])
        if entry is None:
            await interaction.response.send_message(
                "That entry is no longer available. Close the menu and open it again.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            EditReasonModal(self.view, self.category, entry)
        )


class EditReasonModal(discord.ui.Modal, title="Edit entry reason"):
    reason = discord.ui.Label(
        text="Reason",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=True,
            max_length=1024,
        ),
    )

    def __init__(self, panel, category: str, entry: Entry):
        super().__init__(timeout=300)
        self.panel = panel
        self.category = category
        self.entry_id, self.old_reason = entry[0], entry[1]
        self.reason.component.default = self.old_reason  # a modal copies its items per instance

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_reason = " ".join(self.reason.component.value.split())

        if new_reason == (self.old_reason or ""):
            await interaction.response.send_message("The reason is unchanged.", ephemeral=True)
            return

        await interaction.response.defer()

        changed = await self.panel.bot.moddb.edit_user_entry(
            self.panel.info.member, self.category, self.entry_id, new_reason
        )
        if changed:
            notice = f"Updated the reason of a {self.category} entry."
        else:
            notice = f"That {self.category} entry no longer exists, nothing was changed."

        await interaction.edit_original_response(
            view=await reopened_panel(self.panel, notice=notice)
        )
