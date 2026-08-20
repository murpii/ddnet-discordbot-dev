from __future__ import annotations

import contextlib
import logging

from pathlib import Path
from typing import Optional

import discord

from .mappings import TRANSCRIPT_THREADS
from .ticket import Ticket, TicketCategory
from .views.containers.transcript import TranscriptContainer
from utils.checks import is_staff
from utils.misc import resolve_active_thread
from utils.text import mask_ip
from utils.transcript import ChannelTranscript, TranscriptBundle

log = logging.getLogger("tickets")


class TicketTranscript(ChannelTranscript):
    """
    Create transcripts + attachment zips for a ticket channel and its threads, then upload them.
    """

    def __init__(self, bot, ticket: Ticket):
        ticket_dir = Path("data/ticket-system")
        super().__init__(
            bot,
            transcripts_dir=ticket_dir / "transcripts-temp",
            attachments_dir=ticket_dir / "attachments-temp",
        )

        self.ticket = ticket
        self.main_transcript: TranscriptBundle | None = None
        self.thread_transcripts: list[TranscriptBundle] = []
        self.closer: Optional[discord.abc.User] = None

    async def run(
            self,
            interaction: Optional[discord.Interaction] = None,
            postscript: Optional[str] = None,
            closer: Optional[discord.abc.User] = None,
    ) -> None:
        """Build the transcript, DM it to the ticket creator, then clean up temp files."""
        self.closer = closer or (interaction.user if interaction else None)
        await self.create_transcript(interaction)
        await self.notify_ticket_creator(postscript)
        self.cleanup()

    async def create_transcript(self, interaction: Optional[discord.Interaction] = None) -> None:
        await self.send_or_edit(interaction, content="Collecting messages...")

        # build ticket channel transcript
        main_transcript = await self.build(
            self.ticket.channel,
            name=f"{self.sanitize_name(self.ticket.channel.name)}-{self.ticket.channel.id}",
            skip_lines=2,
            header_lines=self.info_header(),
        )
        if main_transcript is None:
            await self.send_or_edit(interaction, content="Less than 2 messages found, skipping...")
            return

        self.main_transcript = main_transcript

        # Threads transcript if any exist
        for thread in await self.collect_threads(self.ticket.channel):
            thread_transcript = await self.build(
                thread,
                name=f"{self.sanitize_name(thread.name)}-{thread.id}",
            )
            if thread_transcript:
                self.thread_transcripts.append(thread_transcript)

        await self.upload_files(interaction)

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

        if cat in (TicketCategory.BAN_APPEAL, TicketCategory.VPN_BAN_APPEAL):
            if self.ticket.appeal_data:
                a = self.ticket.appeal_data
                return [
                    title,
                    divider,
                    # store a truncated IP only; the full address is never written to the transcript
                    f"IP: {mask_ip(a.address)} | {a.dnsbl}",
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

        # The TH_* targets are threads, fetch + unarchive them so an archived
        # transcript thread can still be found and written to
        target_channel = await resolve_active_thread(
            self.bot, TRANSCRIPT_THREADS.get(self.ticket.category)
        )
        if target_channel is None:
            log.warning("No target channel found for category %s", self.ticket.category)
            return

        ticket_number = self.ticket.channel.name.rsplit("-", 1)[-1]

        if self.closer:
            closed_by = f"<@{self.closer.id}> (Global Name: {self.closer})"
        else:
            closed_by = "the system (automated close)"
        header = (
            f"**Ticket #{ticket_number}** (Channel ID: {self.ticket.channel.id})\n"
            f"\"{self.ticket.category.value.title()}\" "
            f"Ticket created by: <@{self.ticket.creator.id}> "
            f"(Global Name: {self.ticket.creator}) "
            f"and closed by {closed_by}"
        )

        bundles = ([self.main_transcript] if self.main_transcript else []) + self.thread_transcripts
        await self.upload(target_channel, bundles, header)

    async def send_or_edit(self, interaction: Optional[discord.Interaction], content: str) -> None:
        # progress is only shown when a user is waiting on an interaction. For an
        # automated/bulk close there's nothing to update, and posting into the
        # channel would both pollute the transcript and hit a channel we're about
        # to delete, so skip quietly.
        if interaction:
            await interaction.edit_original_response(content=content)

    async def notify_ticket_creator(
            self,
            postscript: Optional[str] = None,
    ) -> None:
        closed_by_staff = bool(
            self.closer
            and is_staff(
                self.closer,
                roles="mods",
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
