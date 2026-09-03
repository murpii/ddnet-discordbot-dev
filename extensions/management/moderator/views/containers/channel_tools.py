import logging
from typing import Optional

import discord

from utils.containers import ChannelToolView, NoticeView, OptionSelect

log = logging.getLogger()

SLOWMODE_CHOICES = [
    discord.SelectOption(label="Off", value="0"),
    discord.SelectOption(label="5 seconds", value="5"),
    discord.SelectOption(label="10 seconds", value="10"),
    discord.SelectOption(label="30 seconds", value="30"),
    discord.SelectOption(label="1 minute", value="60"),
    discord.SelectOption(label="5 minutes", value="300"),
    discord.SelectOption(label="10 minutes", value="600"),
    discord.SelectOption(label="30 minutes", value="1800"),
    discord.SelectOption(label="1 hour", value="3600"),
    discord.SelectOption(label="6 hours", value="21600"),
]


class SlowmodeView(ChannelToolView):
    title = "Slowmode"
    instructions = "Pick a channel and a delay, then press Apply."

    def __init__(self):
        self.delay: Optional[str] = None
        super().__init__()

    def extra_rows(self) -> list:
        return [
            discord.ui.ActionRow(OptionSelect("Pick a delay", "delay", SLOWMODE_CHOICES)),
            discord.ui.ActionRow(ApplySlowmodeButton()),
        ]


class ApplySlowmodeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Apply", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await self.view.require_channel(interaction)
        if channel is None:
            return
        if self.view.delay is None:
            await interaction.response.send_message(
                view=NoticeView("Pick a delay first."), ephemeral=True
            )
            return

        seconds = int(self.view.delay)
        try:
            await channel.edit(
                slowmode_delay=seconds,
                reason=f"Slowmode set by {interaction.user} via moderation hub",
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                view=NoticeView(f"I am not allowed to edit {channel.mention}.")
            )
            return

        log.info("ModHub: %s set slowmode to %ds in #%s", interaction.user, seconds, channel)
        if seconds == 0:
            outcome = f"Slowmode disabled in {channel.mention}."
        else:
            outcome = f"Slowmode set to {seconds} seconds in {channel.mention}."
        await interaction.response.edit_message(view=NoticeView(outcome))


PURGE_CHOICES = [
    discord.SelectOption(label=f"{amount} messages", value=str(amount))
    for amount in (5, 10, 25, 50, 100)
]


class PurgeView(ChannelToolView):
    title = "Purge messages"
    instructions = (
        "Bulk-delete the newest messages of a channel.\n"
        "-# Messages older than 14 days can't be bulk-deleted (Discord limit)."
    )

    def __init__(self):
        self.amount: Optional[str] = None
        super().__init__()

    def extra_rows(self) -> list:
        return [
            discord.ui.ActionRow(OptionSelect("How many messages?", "amount", PURGE_CHOICES)),
            discord.ui.ActionRow(PurgeButton()),
        ]


class PurgeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Purge", style=discord.ButtonStyle.danger)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await self.view.require_channel(interaction)
        if channel is None:
            return
        if self.view.amount is None:
            await interaction.response.send_message(
                view=NoticeView("Pick an amount first."), ephemeral=True
            )
            return

        # purging can take a few seconds, lock in the response first
        await interaction.response.defer()
        try:
            deleted = await channel.purge(
                limit=int(self.view.amount),
                reason=f"Purge by {interaction.user} via moderation hub",
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                view=NoticeView(f"I am not allowed to delete messages in {channel.mention}.")
            )
            return
        except discord.HTTPException:
            await interaction.edit_original_response(
                view=NoticeView("Purge failed (messages may be older than 14 days).")
            )
            return

        log.info("ModHub: %s purged %d messages in #%s", interaction.user, len(deleted), channel)
        await interaction.edit_original_response(
            view=NoticeView(f"Deleted {len(deleted)} messages in {channel.mention}.")
        )


class LockView(ChannelToolView):
    title = "Lock / unlock channel"
    instructions = (
        "Locking denies Send Messages for @everyone in the picked channel.\n"
        "Unlocking resets the permission to inherit again."
    )

    def extra_rows(self) -> list:
        return [discord.ui.ActionRow(LockButton(lock=True), LockButton(lock=False))]


class LockButton(discord.ui.Button):
    def __init__(self, *, lock: bool):
        style = discord.ButtonStyle.danger if lock else discord.ButtonStyle.success
        super().__init__(label="Lock" if lock else "Unlock", style=style)  # noqa
        self.lock = lock

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await self.view.require_channel(interaction)
        if channel is None:
            return

        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False if self.lock else None  # None = inherit
        try:
            await channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"{'Locked' if self.lock else 'Unlocked'} by {interaction.user} via moderation hub",
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                view=NoticeView(f"I am not allowed to edit permissions of {channel.mention}.")
            )
            return

        log.info("ModHub: %s %s #%s", interaction.user, "locked" if self.lock else "unlocked", channel)
        word = "locked" if self.lock else "unlocked"
        await interaction.response.edit_message(
            view=NoticeView(f"{channel.mention} has been {word}.")
        )
