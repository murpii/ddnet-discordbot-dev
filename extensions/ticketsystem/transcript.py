from __future__ import annotations

import contextlib
import json
import logging
import os
import zipfile

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, TypeAlias

import discord

from .ticket import Ticket, TicketCategory
from .views.containers.transcript import TranscriptContainer
from constants import Channels, Roles
from utils.checks import is_staff

log = logging.getLogger("tickets")

MAX_ZIP_SIZE = 5 * 1024 * 1024
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024

AttachmentBytes: TypeAlias = bytes
AttachmentItem: TypeAlias = tuple[str, AttachmentBytes]


class FileTooLargeError(Exception):
    pass


@dataclass(slots=True)
class TranscriptBundle:
    transcript_path: Path
    zip_paths: list[Path]

    def __repr__(self) -> str:
        return json.dumps(
            {
                "transcript_path": str(self.transcript_path),
                "zip_paths": str(self.zip_paths),
            },
            indent=4
        )


class TicketTranscript:
    """
    Create transcripts + attachment zips for a ticket channel and its threads, then upload them.

    Main goals of the refactor:
    - Single pipeline to build transcript/attachments for any Messageable (channel/thread).
    - One zip writer that supports "split into multiple zip files by size" and returns a name->zip mapping.
    - Pathlib and context managers.
    - Fix thread zip mapping bug (filenames -> specific zip file).
    """

    def __init__(self, bot, ticket: Ticket):
        self.bot = bot
        self.ticket = ticket

        self.ticket_dir = Path("data/ticket-system")
        self.transcripts_dir = self.ticket_dir / "transcripts-temp"
        self.attachments_dir = self.ticket_dir / "attachments-temp"

        self.files_to_cleanup: set[Path] = set()

        self.main_transcript: TranscriptBundle | None = None
        self.thread_transcripts: list[TranscriptBundle] = []

        self._seen_attachment_names: set[str] = set()

    async def create_transcript(self, interaction: Optional[discord.Interaction] = None) -> None:
        await self.send_or_edit(interaction, content="Collecting messages...")

        # build ticket channel transcript
        main_transcript = await self.build_transcript(
            target=self.ticket.channel,
            transcript_name=f"{self.sanitize_name(self.ticket.channel.name)}-{self.ticket.channel.id}",
            interaction=interaction,
            skip_lines=3,
            header_lines=self.info_header(),
        )
        if main_transcript is None:
            await self.send_or_edit(interaction, content="Less than 2 messages found, skipping...")
            return

        self.main_transcript = main_transcript

        # Threads transcript if any exist
        for thread in await self.collect_threads():
            thread_transcript = await self.build_transcript(
                target=thread,
                transcript_name=f"{self.sanitize_name(thread.name)}-{thread.id}",
                interaction=None,  # keep thread work quiet; you can pass interaction if desired
                skip_lines=0,
                header_lines=None,
            )
            if thread_transcript:
                self.thread_transcripts.append(thread_transcript)

        await self.upload_files(interaction)

    async def collect_threads(self) -> list[discord.Thread]:
        threads = list(self.ticket.channel.threads)
        async for thread in self.ticket.channel.archived_threads(limit=None):
            threads.append(thread)
        return threads

    async def build_transcript(
            self,
            *,
            target: discord.abc.Messageable,
            transcript_name: str,
            interaction: Optional[discord.Interaction],
            skip_lines: int,
            header_lines: Optional[list[str]],
    ) -> TranscriptBundle | None:
        messages: list[str] = []
        attachments: list[AttachmentItem] = []

        if header_lines:
            messages.extend(header_lines)

        # Collect + process messages
        processed_count = 0
        async for msg in target.history(limit=None, oldest_first=True):
            # Skips lines (usually the first 3 embeds of a ticket channel)
            processed_count += 1
            if processed_count <= skip_lines:
                continue

            content, attachment_items = await self.process_message(msg)
            messages.append(content)
            attachments.extend(attachment_items)

        if not messages:
            return None

        # Zip attachments (if any) and annotate transcript lines with zip info
        zip_paths: list[Path] = []
        if attachments:
            if interaction:
                await self.send_or_edit(interaction, content="Compressing files...")
            zip_paths, name_to_zip = self.compress_files(
                transcript_name=transcript_name,
                attachments=attachments,
            )
            messages = [self.format_transcript_with_zip_locations(m, name_to_zip) for m in messages]

        # write transcript
        transcript_path = self.transcripts_dir / f"{transcript_name}.txt"
        transcript_path.write_text("\n".join(messages), encoding="utf-8")

        # for the cleanup later
        self.tracked_files(transcript_path)
        for z in zip_paths:
            self.tracked_files(z)
        b = TranscriptBundle(transcript_path=transcript_path, zip_paths=zip_paths)
        return TranscriptBundle(transcript_path=transcript_path, zip_paths=zip_paths)

    def compress_files(
            self, *, transcript_name: str, attachments: Iterable[AttachmentItem]
    ) -> tuple[list[Path], dict[str, Path]]:
        zip_paths: list[Path] = []
        name_to_zip: dict[str, Path] = {}

        zip_number = 1
        current_size = 0
        current_zip: zipfile.ZipFile | None = None
        current_zip_path: Path | None = None

        def open_new_zip() -> tuple[zipfile.ZipFile, Path]:
            nonlocal zip_number
            path = self.attachments_dir / f"{transcript_name}_{zip_number}.zip"
            zip_number += 1
            return zipfile.ZipFile(path, "w", zipfile.ZIP_STORED), path

        try:
            for name, data in attachments:
                data_size = len(data)

                if data_size > MAX_ZIP_SIZE:
                    raise ValueError(f"Attachment {name} exceeds MAX_ZIP_SIZE")

                if current_zip is None or current_size + data_size > MAX_ZIP_SIZE:
                    if current_zip is not None:
                        current_zip.close()
                        zip_paths.append(current_zip_path)

                    current_size = 0
                    current_zip, current_zip_path = open_new_zip()

                current_zip.writestr(name, data)
                name_to_zip[name] = current_zip_path
                current_size += data_size

            if current_zip is not None:
                current_zip.close()
                zip_paths.append(current_zip_path)

        finally:
            with contextlib.suppress(Exception):
                if current_zip is not None:
                    current_zip.close()

        return zip_paths, name_to_zip  # noqa

    @staticmethod
    def format_transcript_with_zip_locations(message: str, name_to_zip: dict[str, Path]) -> str:
        lines = message.split("\n")
        out: list[str] = []

        for line in lines:
            if line.startswith("Attachments:"):
                out.append(line)
                continue

            if zip_path := name_to_zip.get(line):
                out.append(f"{line} (Stored in: {zip_path.name})")
            else:
                out.append(line)

        return "\n".join(out)

    async def process_message(self, message: discord.Message) -> tuple[str, list[AttachmentItem]]:
        created_at = message.created_at.replace(second=0, microsecond=0, tzinfo=None)
        content = f"{created_at} {message.author}: {message.content}"
        attachment_items: list[AttachmentItem] = []

        if message.attachments:
            content += "\nAttachments:\n"
            for a in message.attachments:
                if a.size > MAX_ATTACHMENT_SIZE:
                    raise FileTooLargeError(
                        f"Attachment exceeds MAX_ATTACHMENT_SIZE ({MAX_ATTACHMENT_SIZE} bytes)\n"
                        f"Either increase limit or delete attachment {a} ({message.jump_url}) and try again."
                    )
                name = self.unique_attachment_name(a.filename)
                content += f"{name}\n"
                attachment_items.append((name, await a.read()))

        if message.embeds and message.author.bot:
            embed = message.embeds[0]
            content += "\nEmbeds:\n"
            if embed.title:
                content += f"Title: {embed.title}\n"
            if embed.description:
                content += f"Description: {embed.description}\n"
            for field in (embed.fields or []):
                content += f"{field.name}: {field.value}\n"

        return content, attachment_items

    def unique_attachment_name(self, filename: str) -> str:
        if filename not in self._seen_attachment_names:
            self._seen_attachment_names.add(filename)
            return filename

        if "." in filename:
            base, ext = filename.rsplit(".", 1)
            ext = f".{ext}"
        else:
            base, ext = filename, ""

        counter = 1
        new_filename = f"{base}_{counter}{ext}"
        while new_filename in self._seen_attachment_names:
            counter += 1
            new_filename = f"{base}_{counter}{ext}"

        self._seen_attachment_names.add(new_filename)
        return new_filename

    def info_header(self) -> list[str]:
        cat = self.ticket.category
        title = f"{cat.value.title()} Ticket Transcript:"
        divider = "=" * max(10, len(title))

        if cat == TicketCategory.RENAME:
            if self.ticket.rename_data:
                return [
                    title, divider, f"Old name:\n{self.ticket.rename_data.old_profile}\n"
                                    f"New name:\n{self.ticket.rename_data.new_profile}"
                ]
            return [title, divider, "Missing data.\n"]

        if cat == TicketCategory.BAN_APPEAL:
            if self.ticket.appeal_data:
                a = self.ticket.appeal_data
                return [
                    title,
                    divider,
                    f"IP: {a.address} | {a.dnsbl}",
                    f"Name: {a.name}",
                    f"Reason: {a.reason}",
                    f"Appeal: {a.appeal}\n",
                ]
            return [title, divider, "Missing data.\n"]

        return []

    async def upload_files(self, interaction: discord.Interaction) -> None:
        if not self.main_transcript and not self.thread_transcripts:
            return

        await self.send_or_edit(interaction, content="Uploading files...")

        transcript_categories = {
            TicketCategory.REPORT: Channels.TH_REPORTS,
            TicketCategory.BAN_APPEAL: Channels.TH_BAN_APPEALS,
            TicketCategory.RENAME: Channels.TH_RENAMES,
            TicketCategory.COMPLAINT: Channels.TH_COMPLAINTS,
            TicketCategory.ADMIN_MAIL: Channels.TH_ADMIN_MAIL,
            TicketCategory.COMMUNITY_APP: Channels.TH_COMMUNITY_APPS,
        }

        target_channel = self.bot.get_channel(transcript_categories.get(self.ticket.category))
        if target_channel is None:
            log.warning("No target channel found for category %s", self.ticket.category)
            return

        header = (
            f"**Ticket Channel ID: {self.ticket.channel.id}**\n"
            f"\"{self.ticket.category.value.title()}\" "
            f"Ticket created by: <@{self.ticket.creator.id}> "
            f"(Global Name: {self.ticket.creator}) "
            f"and closed by <@{interaction.user.id}> "
            f"(Global Name: {interaction.user})"
        )

        allowed = discord.AllowedMentions(users=False)

        # Main transcript first
        if self.main_transcript:
            await target_channel.send(
                header,
                files=[discord.File(self.main_transcript.transcript_path)],
                allowed_mentions=allowed,
            )
            for zp in self.main_transcript.zip_paths:
                await target_channel.send(files=[discord.File(zp)], allowed_mentions=allowed)

        # Then thread transcripts + zips
        for bundle in self.thread_transcripts:
            await target_channel.send(files=[discord.File(bundle.transcript_path)], allowed_mentions=allowed)
            for zp in bundle.zip_paths:
                await target_channel.send(files=[discord.File(zp)], allowed_mentions=allowed)

    async def send_or_edit(self, interaction: Optional[discord.Interaction], content: str) -> None:
        if interaction:
            await interaction.edit_original_response(content=content)
        else:
            await self.ticket.channel.send(content)

    async def notify_ticket_creator(
            self,
            interaction: Optional[discord.Interaction],
            postscript: Optional[str] = None,
    ) -> None:
        closed_by_staff = bool(
            interaction
            and is_staff(
                interaction.user,
                roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR],
            )
        )

        if not closed_by_staff and (not self.main_transcript):
            return

        file: discord.File | None = None
        filename: str | None = None

        if self.main_transcript:
            filename = self.main_transcript.transcript_path.name
            file = discord.File(self.main_transcript.transcript_path, filename=filename)

        with contextlib.suppress(discord.Forbidden):
            await self.ticket.creator.send(
                file=file,
                view=TranscriptContainer(
                    ticket=self.ticket,
                    closed_by_staff=closed_by_staff,
                    postscript=postscript,
                    transcript_filename=filename,
                ),
            )

    def cleanup(self) -> None:
        for path in list(self.files_to_cleanup):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()

    def tracked_files(self, path: Path) -> None:
        self.files_to_cleanup.add(path)

    @staticmethod
    def sanitize_name(name: str) -> str:
        # Windows-safe filename sanitization
        return "".join(c for c in name if c not in r'\/:*?"<>|').strip() or "thread"
