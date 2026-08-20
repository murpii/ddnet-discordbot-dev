from __future__ import annotations

import contextlib
import json
import logging
import zipfile

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import discord

log = logging.getLogger("transcript")

DEFAULT_MAX_ZIP_SIZE_MB = 8
DEFAULT_MAX_ATTACHMENT_SIZE_MB = 8


def config_size_bytes(config, option: str, default_mb: int) -> int:
    try:
        mb = config.getint("TRANSCRIPTS", option, fallback=default_mb)
    except ValueError:
        mb = default_mb
    return mb * 1024 * 1024


class FileTooLargeError(Exception):
    pass


def remove_files(paths) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("Could not delete %s: %s", path, e)


@dataclass(slots=True)
class TranscriptBundle:
    transcript_path: Path
    zip_paths: list[Path] = field(default_factory=list)
    message_count: int = 0

    def __repr__(self) -> str:
        return json.dumps(
            {
                "transcript_path": str(self.transcript_path),
                "zip_paths": [str(p) for p in self.zip_paths],
                "message_count": self.message_count,
            },
            indent=4
        )


class ZipWriter:
    def __init__(self, directory: Path, base_name: str, max_size: int):
        self.directory = directory
        self.base_name = base_name
        self.max_size = max_size

        self.paths: list[Path] = []
        self.current: zipfile.ZipFile | None = None
        self.current_path: Path | None = None
        self.current_size = 0

    def add(self, name: str, data: bytes) -> Path:
        if len(data) > self.max_size:
            raise ValueError(f"{name} is larger than a single zip may be")

        if self.current is None or self.current_size + len(data) > self.max_size:
            self.open_next()

        self.current.writestr(name, data)
        self.current_size += len(data)
        return self.current_path

    def open_next(self) -> None:
        self.close()
        path = self.directory / f"{self.base_name}_{len(self.paths) + 1}.zip"
        self.current = zipfile.ZipFile(path, "w", zipfile.ZIP_STORED)
        self.current_path = path
        self.current_size = 0

    def close(self) -> list[Path]:
        if self.current is not None:
            with contextlib.suppress(Exception):
                self.current.close()
            self.paths.append(self.current_path)
            self.current = None
            self.current_path = None
            self.current_size = 0
        return self.paths


class ChannelTranscript:
    def __init__(
            self,
            bot,
            *,
            transcripts_dir: Path,
            attachments_dir: Path,
            keep_files: bool = False,
            skip_oversized: bool = False,
            max_zip_size_mb: Optional[int] = None,
            max_attachment_size_mb: Optional[int] = None,
    ):
        self.bot = bot
        self.transcripts_dir = transcripts_dir
        self.attachments_dir = attachments_dir
        self.keep_files = keep_files
        self.skip_oversized = skip_oversized
        self.max_zip_size = (
            max_zip_size_mb * 1024 * 1024 if max_zip_size_mb
            else config_size_bytes(bot.config, "MAX_ZIP_SIZE_MB", DEFAULT_MAX_ZIP_SIZE_MB)
        )
        self.max_attachment_size = (
            max_attachment_size_mb * 1024 * 1024 if max_attachment_size_mb
            else config_size_bytes(bot.config, "MAX_ATTACHMENT_SIZE_MB", DEFAULT_MAX_ATTACHMENT_SIZE_MB)
        )

        self.files_to_cleanup: set[Path] = set()
        self.seen_attachment_names: set[str] = set()

    async def build(
            self,
            target: discord.abc.Messageable,
            *,
            name: str,
            skip_lines: int = 0,
            header_lines: Optional[list[str]] = None,
            limit: Optional[int] = None,
            after: Optional[datetime] = None,
    ) -> TranscriptBundle | None:
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

        oldest_first = limit is None
        zip_writer = ZipWriter(self.attachments_dir, name, self.max_zip_size)
        lines: list[str] = []
        seen = 0

        try:
            async for message in target.history(limit=limit, after=after, oldest_first=oldest_first):
                seen += 1
                if oldest_first and seen <= skip_lines:
                    continue
                lines.append(await self.process_message(message, zip_writer))
        except Exception:
            remove_files(zip_writer.close())
            raise

        zip_paths = zip_writer.close()
        message_count = len(lines)
        if not oldest_first:
            lines.reverse()
        if header_lines:
            lines = list(header_lines) + lines

        if not lines:
            remove_files(zip_paths)
            return None

        transcript_path = self.transcripts_dir / f"{name}.txt"
        transcript_path.write_text("\n".join(lines), encoding="utf-8")

        self.tracked_files(transcript_path)
        for path in zip_paths:
            self.tracked_files(path)
        return TranscriptBundle(
            transcript_path=transcript_path, zip_paths=zip_paths, message_count=message_count
        )

    async def process_message(self, message: discord.Message, zip_writer: ZipWriter) -> str:
        created_at = message.created_at.replace(second=0, microsecond=0, tzinfo=None)
        content = f"{created_at} {message.author}: {message.content}"

        if component_text := self.extract_component_text(message.components):
            block = "\n".join(component_text)
            content += block if not message.content else f"\n{block}"

        if message.attachments:
            content += "\nAttachments:\n"
            for attachment in message.attachments:
                content += f"{await self.store_attachment(attachment, zip_writer, message)}\n"

        if message.embeds and message.author.bot:
            embed = message.embeds[0]
            content += "\nEmbeds:\n"
            if embed.title:
                content += f"Title: {embed.title}\n"
            if embed.description:
                content += f"Description: {embed.description}\n"
            for field in (embed.fields or []):
                content += f"{field.name}: {field.value}\n"

        return content

    async def store_attachment(
            self, attachment: discord.Attachment, zip_writer: ZipWriter, message: discord.Message
    ) -> str:
        limit_mb = self.max_attachment_size // 1024 // 1024

        if attachment.size > self.max_attachment_size:
            if not self.skip_oversized:
                raise FileTooLargeError(
                    f"Attachment {attachment.filename!r} is {attachment.size / 1024 / 1024:.1f} MB, over the "
                    f"{limit_mb} MB limit.\n"
                    f"Raise MAX_ATTACHMENT_SIZE_MB in config.ini, or delete the attachment "
                    f"({message.jump_url}) and try again."
                )
            return f"{attachment.filename} (skipped, over {limit_mb} MB) {attachment.url}"

        name = self.unique_attachment_name(attachment.filename)
        try:
            data = await attachment.read()
        except (discord.HTTPException, discord.NotFound) as e:
            log.warning("Could not download %s: %s", attachment.filename, e)
            return f"{name} (download failed) {attachment.url}"

        zip_path = zip_writer.add(name, data)
        return f"{name} (Stored in: {zip_path.name})"

    @staticmethod
    async def collect_threads(channel) -> list[discord.Thread]:
        if not hasattr(channel, "archived_threads"):
            return []

        threads = list(channel.threads)
        async for thread in channel.archived_threads(limit=None):
            threads.append(thread)
        return threads

    async def upload(
            self,
            target: discord.abc.Messageable,
            bundles: list[TranscriptBundle],
            header: Optional[str] = None,
    ) -> None:
        for index, bundle in enumerate(bundles):
            await self.send_file(target, bundle.transcript_path, header if index == 0 else None)
            for zip_path in bundle.zip_paths:
                await self.send_file(target, zip_path)

    @staticmethod
    async def send_file(
            target: discord.abc.Messageable, path: Path, content: Optional[str] = None
    ) -> None:
        upload = discord.File(path)
        try:
            await target.send(
                content, files=[upload], allowed_mentions=discord.AllowedMentions(users=False)
            )
        finally:
            upload.close()

    @staticmethod
    def extract_component_text(components) -> list[str]:
        lines: list[str] = []

        def walk(items) -> None:
            for item in items:
                text = getattr(item, "content", None)
                if isinstance(text, str) and text:
                    lines.append(text)
                if children := getattr(item, "children", None):
                    walk(children)

        walk(components)
        return lines

    def unique_attachment_name(self, filename: str) -> str:
        if filename not in self.seen_attachment_names:
            self.seen_attachment_names.add(filename)
            return filename

        if "." in filename:
            base, ext = filename.rsplit(".", 1)
            ext = f".{ext}"
        else:
            base, ext = filename, ""

        counter = 1
        new_filename = f"{base}_{counter}{ext}"
        while new_filename in self.seen_attachment_names:
            counter += 1
            new_filename = f"{base}_{counter}{ext}"

        self.seen_attachment_names.add(new_filename)
        return new_filename

    def cleanup(self) -> None:
        if self.keep_files:
            return
        remove_files(self.files_to_cleanup)

    def tracked_files(self, path: Path) -> None:
        self.files_to_cleanup.add(path)

    @staticmethod
    def sanitize_name(name: str) -> str:
        return "".join(c for c in name if c not in r'\/:*?"<>|').strip() or "thread"
