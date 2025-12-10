from datetime import datetime
from typing import Optional, List, Tuple
import discord

from extensions.moderator.manager import MemberInfo
from extensions.moderator.embeds import NoMemberInfoEmbed, full_info


class RemoveEntryButton(discord.ui.Button):
    def __init__(self, bot, member: discord.abc.User, *, disabled: bool = False):
        super().__init__(
            label="Remove Entry",
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )
        self.bot = bot
        self.db = bot.moddb
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.member)

        if not info:
            await interaction.response.edit_message(
                content=f"No moderation entries found for {self.member}.",
                embeds=[NoMemberInfoEmbed()],
                view=None,
            )
            return

        new_view = EntryCategoryView(self.db, info)
        await interaction.response.edit_message(
            content=f"Choose which entries to remove for {info.member}:",
            view=new_view,
        )


class EntryCategoryView(discord.ui.View):
    def __init__(self, db, info: MemberInfo, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.db = db
        self.info = info

        has_timeouts = bool(info.timeout_reasons)
        has_kicks = bool(info.kick_reasons)
        has_bans = bool(info.ban_reasons)

        self.add_item(
            EntryCategoryButton(
                "Timeout", "timeout", db, info, disabled=not has_timeouts
            )
        )
        self.add_item(
            EntryCategoryButton("Kick", "kick", db, info, disabled=not has_kicks)
        )
        self.add_item(
            EntryCategoryButton("Ban", "ban", db, info, disabled=not has_bans)
        )


class EntryCategoryButton(discord.ui.Button):
    def __init__(
            self,
            label: str,
            category: str,  # "timeout" | "kick" | "ban"
            db,
            info: MemberInfo,
            *,
            disabled: bool = False,
    ):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )
        self.category = category
        self.db = db
        self.info = info

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.category == "timeout":
            entries = self.info.timeout_reasons
        elif self.category == "kick":
            entries = self.info.kick_reasons
        elif self.category == "ban":
            entries = self.info.ban_reasons
        else:
            await interaction.response.send_message(
                "Unknown category.", ephemeral=True
            )
            return

        if not entries:
            await interaction.response.send_message(
                f"No {self.category} entries found for this user.",
                ephemeral=True,
            )
            return

        new_view = EntrySelectView(self.db, self.info, self.category, entries)
        await interaction.response.edit_message(
            content=f"Select the {self.category} entry you want to remove:",
            view=new_view,
        )


class EntrySelect(discord.ui.Select):
    def __init__(
            self,
            db,
            info: MemberInfo,
            category: str,
            entries: List[Tuple[str, datetime]],
    ):
        self.db = db
        self.info = info
        self.category = category
        self.entries = entries

        options: List[discord.SelectOption] = []
        # max 25 options per select
        for idx, (reason, ts) in enumerate(entries[:25], start=1):
            label = f"{idx}. {ts.strftime('%Y-%m-%d %H:%M')}"
            desc = reason if len(reason) <= 90 else f"{reason[:87]}..."
            options.append(
                discord.SelectOption(
                    label=label,
                    description=desc,
                    value=str(idx - 1),
                )
            )

        placeholder = f"Select one or more {category} entries to remove"
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            selected_indices = sorted({int(v) for v in self.values})
        except ValueError:
            await interaction.response.send_message(
                "Invalid selection.",
                ephemeral=True,
            )
            return

        to_delete: List[Tuple[str, datetime]] = []
        for idx in selected_indices:
            try:
                to_delete.append(self.entries[idx])
            except IndexError:
                continue

        if not to_delete:
            await interaction.response.send_message(
                "Selected entries are no longer available.",
                ephemeral=True,
            )
            return

        deleted_any = False
        for reason, timestamp in to_delete:
            deleted = await self.db.remove_user_entry(
                member=self.info.member,
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

        # Refresh info once after deletions
        info: Optional[MemberInfo] = await self.db.fetch_user_info(self.info.member)

        if not info:
            await interaction.response.edit_message(
                content=(
                    f"Removed {len(to_delete)} {self.category} "
                    f"entr{'y' if len(to_delete) == 1 else 'ies'}.\n"
                    f"No more moderation entries for {self.info.member}."
                ),
                embeds=[NoMemberInfoEmbed()],
                view=None,
            )
            return

        has_any_entries = bool(
            info.timeout_reasons or info.kick_reasons or info.ban_reasons
        )

        from extensions.moderator.views.info import MemberModerationView
        view = MemberModerationView(
            bot=interaction.client,
            info=info,
            can_remove_entries=has_any_entries,
        )

        updated_embeds = full_info(info)

        await interaction.response.edit_message(
            content=(
                f"Removed {len(to_delete)} {self.category} "
                f"entr{'y' if len(to_delete) == 1 else 'ies'}."
            ),
            embeds=updated_embeds,
            view=view,
        )


class EntrySelectView(discord.ui.View):
    def __init__(
            self,
            db,
            info: MemberInfo,
            category: str,
            entries: List[Tuple[str, datetime]],
            *,
            timeout: float | None = 180,
    ):
        super().__init__(timeout=timeout)
        self.add_item(EntrySelect(db, info, category, entries))
