from datetime import datetime
from typing import List, Tuple

import discord

from utils.containers import INFO_ACCENT, separator
from utils.text import clip


def category_entries(info, category: str) -> List[Tuple[str, datetime, str]]:
    return {
        "timeout": info.timeout_reasons,
        "ban": info.ban_reasons,
        "kick": info.kick_reasons,
    }[category]


def removal_container(panel) -> discord.ui.Container:
    """
    Build the removal menu for the panel's current removal step

    Step "category": pick which kind of entry to remove
    Step "select": multi-select of the entries in the picked category
    """
    if panel.removal_step == "select":
        entries = category_entries(panel.info, panel.removal_category)
        return discord.ui.Container(
            discord.ui.TextDisplay(
                f"**Select the {panel.removal_category} entries you want to remove:**"
            ),
            discord.ui.ActionRow(EntrySelect(panel.removal_category, entries)),
            discord.ui.ActionRow(CancelButton()),
            accent_colour=INFO_ACCENT,
        )

    return discord.ui.Container(
        discord.ui.TextDisplay(
            f"**Choose which entries to remove for {panel.info.member.mention}:**"
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


class RemoveEntryButton(discord.ui.Button):
    def __init__(self, *, disabled: bool = False):
        super().__init__(
            label="Remove Entry",
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view  # the UserInfoView this button sits in
        await interaction.response.edit_message(view=panel.with_removal("category"))


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
            view=panel.with_removal("select", self.category)
        )


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        await interaction.response.edit_message(view=panel.with_removal(None))


class EntrySelect(discord.ui.Select):
    def __init__(self, category: str, entries: List[Tuple[str, datetime, str]]):
        self.category = category
        self.entries = entries

        options: List[discord.SelectOption] = []
        # max 25 options per select
        options.extend(
            discord.SelectOption(
                label=f"{idx}. {ts.strftime('%Y-%m-%d %H:%M')}",
                description=clip(reason, 90),
                value=str(idx - 1),
            )
            for idx, (reason, ts, _invoker) in enumerate(entries[:25], start=1)
        )
        super().__init__(
            placeholder=f"Select one or more {category} entries to remove",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        db = panel.bot.moddb

        try:
            selected_indices = sorted({int(v) for v in self.values})
        except ValueError:
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return

        to_delete: List[Tuple[str, datetime, str]] = []
        for idx in selected_indices:
            try:
                to_delete.append(self.entries[idx])
            except IndexError:
                continue

        if not to_delete:
            await interaction.response.send_message(
                "Selected entries are no longer available.", ephemeral=True
            )
            return

        deleted_any = False
        for reason, timestamp, _invoker in to_delete:
            deleted = await db.remove_user_entry(
                member=panel.info.member,
                entry_type=self.category,
                reason=reason,
                timestamp=timestamp,
            )
            if deleted:
                deleted_any = True

        if not deleted_any:
            await interaction.response.send_message(
                "No matching entries were removed (they may already be gone).",
                ephemeral=True,
            )
            return

        notice = (
            f"Removed {len(to_delete)} {self.category} "
            f"entr{'y' if len(to_delete) == 1 else 'ies'}."
        )

        info = await db.fetch_user_info(panel.info.member)

        from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
        if not info:
            await interaction.response.edit_message(view=NoUserInfoView(notice=notice))
            return

        await interaction.response.edit_message(
            view=UserInfoView(panel.bot, info, notice=notice, pages=panel.pages)
        )
