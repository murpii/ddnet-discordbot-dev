import contextlib
import logging

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from constants import Guilds
from utils.checks import staff_only
from utils.transcript import ChannelTranscript, TranscriptBundle

log = logging.getLogger("archive")

STAGING_DIR = Path("data/archives-temp")
ZIP_HEADROOM_MB = 1


def plural(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


@dataclass(slots=True)
class ArchiveResult:
    transcript: ChannelTranscript
    directory: Path
    bundles: list[TranscriptBundle]

    @property
    def messages(self) -> int:
        return sum(b.message_count for b in self.bundles)

    @property
    def files(self) -> int:
        return sum(1 + len(b.zip_paths) for b in self.bundles)

    def clear(self) -> None:
        self.transcript.cleanup()
        with contextlib.suppress(OSError):
            self.directory.rmdir()


class ChannelArchive(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Guilds.DDNET)
    @app_commands.guild_only()
    @staff_only("discord_mods")
    @app_commands.command(
        name="archive",
        description="Post a transcript of a channel into that channel, then optionally lock it.",
    )
    @app_commands.describe(
        channel="Channel to archive. Defaults to the one you run this in.",
        lock="Lock and hide the channel once the transcript is posted.",
        limit="Only archive the newest N messages. Defaults to the full history.",
    )
    async def archive(
            self,
            interaction: discord.Interaction,
            channel: Optional[discord.TextChannel] = None,
            lock: bool = False,
            limit: Optional[app_commands.Range[int, 1, 100000]] = None,
    ):
        channel = channel or interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(  # noqa
                "Only text channels can be archived.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)  # noqa
        await self.run(interaction, channel, lock=lock, limit=limit)

    async def run(
            self,
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            *,
            lock: bool = False,
            limit: Optional[int] = None,
    ) -> None:
        """Build the transcript, post it into the channel, then clear it off disk."""
        try:
            result = await self.build_archive(interaction, channel, limit=limit)
        except Exception as e:
            log.exception("Archiving %s failed:\n%s", channel.name, e)
            await interaction.edit_original_response(content=f"Archiving failed:\n{e}")
            return

        if result is None:
            await interaction.edit_original_response(content="That channel has no messages to archive.")
            return

        await interaction.edit_original_response(content=f"Posting the transcript into {channel.mention}...")
        try:
            await result.transcript.upload(
                channel, result.bundles, self.header(channel, result, interaction.user)
            )
        except discord.HTTPException as e:
            log.warning("Could not post the archive of %s: %s", channel.name, e)
            result.clear()
            await interaction.edit_original_response(
                content=f"Couldn't post the transcript into {channel.mention}:\n{e}"
            )
            return

        result.clear()

        summary = (
            f"Archived {channel.mention}: {plural(result.messages, 'message')} posted as "
            f"{plural(result.files, 'file')} in the channel itself. Nothing was left on disk."
        )
        if lock:
            try:
                summary += f"\n{await self.lock_channel(channel, interaction.user)}"
            except discord.Forbidden:
                summary += "\nI don't have permission to lock the channel."

        await interaction.edit_original_response(content=summary)

    async def build_archive(
            self,
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            *,
            limit: Optional[int] = None,
    ) -> Optional[ArchiveResult]:
        base_name = f"{ChannelTranscript.sanitize_name(channel.name)}-{channel.id}"
        directory = STAGING_DIR / base_name
        cap_mb = max(1, channel.guild.filesize_limit // 1024 // 1024 - ZIP_HEADROOM_MB)

        transcript = ChannelTranscript(
            self.bot,
            transcripts_dir=directory,
            attachments_dir=directory,
            skip_oversized=True,
            max_zip_size_mb=cap_mb,
            max_attachment_size_mb=cap_mb,
        )

        await interaction.edit_original_response(content=f"Collecting messages from {channel.mention}...")
        main = await transcript.build(channel, name=base_name, limit=limit)
        if main is None:
            return None

        bundles = [main]
        for thread in await transcript.collect_threads(channel):
            await interaction.edit_original_response(content=f"Collecting thread {thread.name}...")
            bundle = await transcript.build(
                thread,
                name=f"{transcript.sanitize_name(thread.name)}-{thread.id}",
                limit=limit,
            )
            if bundle:
                bundles.append(bundle)

        return ArchiveResult(transcript=transcript, directory=directory, bundles=bundles)

    @staticmethod
    def header(channel: discord.TextChannel, result: ArchiveResult, user: discord.abc.User) -> str:
        return (
            f"**Transcript of #{channel.name}**\n"
            f"{plural(result.messages, 'message')} in {plural(result.files, 'file')}, "
            f"requested by <@{user.id}>.\n"
            f"-# Save these before you delete the channel, they are stored in it and go with it."
        )

    @staticmethod
    async def lock_channel(channel: discord.TextChannel, user: discord.abc.User) -> str:
        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = False
        overwrite.view_channel = False
        await channel.set_permissions(
            everyone, overwrite=overwrite, reason=f"Channel archived by {user}"
        )
        return "The channel is now locked and hidden."


async def setup(bot):
    await bot.add_cog(ChannelArchive(bot))
