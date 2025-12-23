import contextlib
import os
import zipfile
import discord
import logging
from typing import Optional

from .manager import Ticket, TicketCategory
from utils.checks import is_staff
from constants import Channels, Roles

log = logging.getLogger("tickets")
MAX_ZIP_SIZE = 24 * 1024 * 1024


class TicketTranscript:
    """Handles the creation and management of ticket transcripts.

    This class is responsible for generating transcripts, including collecting messages,
    processing attachments, and notifying the ticket creator.

    Args:
        bot: The bot instance used to manage interactions and fetch ticket data.
        ticket: The ticket object containing information about the ticket channel, category, and creator.
    """

    def __init__(self, bot, ticket: Ticket):
        self.bot = bot
        self.ticket = ticket

        self.transcript_file = None
        self.zipped_files = []
        self.attachments_names = set()
        self.attachment_to_zip_map = {}

    async def create_transcript(self, interaction: Optional[discord.Interaction] = None):
        """|coro|
        Generates a transcript of messages from a ticket channel.

        Args:
            interaction (Optional[discord.Interaction]): The interaction object representing the user's action, if applicable.
        """

        messages = []
        attachments = []

        # Interaction update event
        await self.send_or_edit(interaction, content="Collecting messages...")

        if self.ticket.category == TicketCategory.RENAME:
            if self.ticket.rename_data:
                messages.append(
                    f"{self.ticket.category.value.title()} Ticket Transcript:\n"
                    f"=======================\n"
                    f"Old name:\n{self.ticket.rename_data[0]}\n"
                    f"New name:\n{self.ticket.rename_data[1]}"
                )
            else:
                messages.append(
                    f"{self.ticket.category.value.title()} Ticket Transcript:\n"
                    f"=======================\n"
                    f"Missing data. Ticket was most likely converted from a different category.\n"
                )

        if self.ticket.category == TicketCategory.BAN_APPEAL:
            if self.ticket.appeal_data:
                messages.append(
                    f"{self.ticket.category.value.title()} Ticket Transcript:\n"
                    f"==========================\n"
                    f"IP: {self.ticket.appeal_data.address} | {self.ticket.appeal_data.dnsbl}\n"
                    f"Name: {self.ticket.appeal_data.name}\n"
                    f"Reason: {self.ticket.appeal_data.reason}\n"
                    f"Appeal: {self.ticket.appeal_data.appeal}\n"
                )
            else:
                messages.append(
                    f"{self.ticket.category.value.title()} Ticket Transcript:\n"
                    f"==========================\n"
                    "Missing data. Ticket was most likely converted from a different category.\n"
                )

        messages_in_channel = [message async for message in self.ticket.channel.history(limit=None, oldest_first=True)]
        messages_to_process = messages_in_channel[3:]  # skip first 3 messages

        for message in messages_to_process:
            content, attachment_data = await self.process_message(message)  # noqa
            messages.append(content)
            attachments.extend(attachment_data)

        # Interaction update event
        if not messages:
            await self.send_or_edit(interaction, content="Less than 2 messages found, skipping...")
            return

        if attachments:
            await self.compress(attachments, interaction)

        # I hate this and can't think of a better way, but whatever
        if messages := [self.update_message_with_zip_info(msg) for msg in messages]:
            await self.compile_transcript(messages)
        await self.upload_files(interaction)

    async def process_message(self, message):
        """|coro|
        Processes a message from the ticket channel to extract its content and attachments.

        Args:
            message: The message object to be processed.

        Returns:
            tuple: A tuple containing:
                - str: The formatted message content.
                - list: A list of attachment data, including names and file contents.
        """

        created_at = message.created_at.replace(second=0, microsecond=0, tzinfo=None)
        content = f"{created_at} {message.author}: {message.content}"
        attachment_data = []

        if message.attachments:
            content += "\nAttachments:\n"
            for attachment in message.attachments:
                # 80MB (100MB is discords total upload limit for free users, including bots
                # as long our discord server nitro level remains at Level 3)
                if attachment.size > 80 * 1024 * 1024:
                    content += "\nMessage contained attachment too big to log\n"
                    continue
                attachment_name = self.enum_attachments(attachment.filename)
                content += f"{attachment_name}\n"
                attachment_data.append((attachment_name, await attachment.read()))

        # Includes embeds sent by the bot (The starting message of a ticket)
        if message.embeds and message.author.bot:
            embed = message.embeds[0]
            content += "\nEmbeds:\n"
            if embed.title:
                content += f"Title: {embed.title}\n"
            if embed.description:
                content += f"Description: {embed.description}\n"
            if embed.fields:
                for field in embed.fields:
                    content += f"{field.name}: {field.value}\n"

        return content, attachment_data

    def update_message_with_zip_info(self, message):
        """Updates a message to include information about attached zip files.

        Args:
            message (str): The original message containing attachment information.

        Returns:
            str: The updated message with zip file information included.
        """

        lines = message.split("\n")
        updated_lines = []
        for line in lines:
            if line.startswith("Attachments:"):
                updated_lines.append(line)
            elif line in self.attachment_to_zip_map:
                zip_file_path = self.attachment_to_zip_map[line]
                zip_filename = zip_file_path.split("/")[-1]
                updated_lines.append(f"{line} (Stored in: {zip_filename})")
            else:
                updated_lines.append(line)
        return "\n".join(updated_lines)

    async def compile_transcript(self, messages: list = None):
        """|coro|
        Compiles a list of messages into a transcript file.

        Args:
            messages (list, optional): A list of messages to be included in the transcript.
        """

        if len(messages) <= 1 or not messages:
            messages.append("No other messages found.")

        transcript_data = "\n".join(messages)
        transcript_file = f"data/ticket-system/transcripts-temp/{self.ticket.channel.name}-{self.ticket.channel.id}.txt"
        with open(transcript_file, "w", encoding="utf-8") as transcript:
            transcript.write(transcript_data)
        self.transcript_file = transcript_file

    def enum_attachments(self, attachment_name):
        """Enumerates attachment names to ensure uniqueness.

        Args:
            attachment_name (str): The original name of the attachment.

        Returns:
            str: A unique attachment name, potentially modified to avoid duplicates.
        """
        if attachment_name in self.attachments_names:
            base_name, extension = attachment_name.rsplit(".", 1)
            counter = 1
            while f"{base_name}_{counter}.{extension}" in self.attachments_names:
                counter += 1
            attachment_name = f"{base_name}_{counter}.{extension}"

        self.attachments_names.add(attachment_name)
        return attachment_name

    async def compress(self, attachments, interaction: Optional[discord.Interaction]):
        """|coro|
        Compresses a list of attachments into zip files.

        Args:
            attachments (list): A list of tuples containing attachment names and their corresponding file data.
            interaction (Optional[discord.Interaction]): The interaction object.
        """

        await self.send_or_edit(interaction, content="Compressing files...")

        zip_number = 1
        current_zip_size = 0
        current_zip = None
        attachment_zip_base = (
            f"data/ticket-system/attachments-temp/attachments-"
            f"{self.ticket.channel.name}-{self.ticket.channel.id}"
        )

        for attachment_name, file_data in attachments:
            if current_zip is None or current_zip_size + len(file_data) > MAX_ZIP_SIZE:
                if current_zip is not None:
                    current_zip.close()
                    zip_name = f"{attachment_zip_base}_{zip_number}.zip"
                    self.zipped_files.append(zip_name)
                    zip_number += 1
                current_zip_size = 0
                current_zip = zipfile.ZipFile(
                    f"{attachment_zip_base}_{zip_number}.zip", "w", zipfile.ZIP_STORED
                )

            current_zip.writestr(attachment_name, file_data)
            self.attachment_to_zip_map[attachment_name] = (
                f"{attachment_zip_base}_{zip_number}.zip"
            )
            current_zip_size += len(file_data)

        if current_zip is not None:
            current_zip.close()
            self.zipped_files.append(f"{attachment_zip_base}_{zip_number}.zip")

    async def upload_files(self, interaction: Optional[discord.Interaction]):
        """|coro|
        Uploads transcript and attachment files to the designated channels.

        Args:
            interaction (Optional[discord.Interaction]): The interaction object.
        """

        if not self.transcript_file and not self.zipped_files:
            return

        # Interaction update event
        await self.send_or_edit(interaction, content="Uploading files...")

        targets = {
            TicketCategory.REPORT: Channels.TH_REPORTS,
            TicketCategory.BAN_APPEAL: Channels.TH_BAN_APPEALS,
            TicketCategory.RENAME: Channels.TH_RENAMES,
            TicketCategory.COMPLAINT: Channels.TH_COMPLAINTS,
            TicketCategory.ADMIN_MAIL: Channels.TH_ADMIN_MAIL,
        }

        target_channel = self.bot.get_channel(targets.get(self.ticket.category))

        # TODO: Expand the info messages with all the attached ticket data.
        if interaction:
            msg = (
                f'**Ticket Channel ID: {self.ticket.channel.id}** \n "{self.ticket.category.value.title()}" '
                f"Ticket created by: <@{self.ticket.creator.id}> (Global Name: {self.ticket.creator}) "
                f"and closed by <@{interaction.user.id}> (Global Name: {interaction.user})"
            )
        else:
            msg = (
                f'"{self.ticket.category.value.title()}" '
                f"Ticket created by: <@{self.ticket.creator.id}> (Global Name: {self.ticket.creator}), "
                f"closed due to inactivity. \nTicket Channel ID: {self.ticket.channel.id}"
            )

        try:
            await target_channel.send(
                msg,
                files=(
                    [discord.File(self.transcript_file)]
                    if self.transcript_file
                    else None
                ),
                allowed_mentions=discord.AllowedMentions(users=False),
            )
        except AttributeError as e:
            self.ticket.being_closed = False
            log.error(e)
            return

        for zipped_file in self.zipped_files or []:
            try:
                await target_channel.send(
                    files=[discord.File(zipped_file)],
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
            except discord.HTTPException:
                log.error("Couldn't upload zipped files, request entity too large.")
                return

    async def send_or_edit(self, interaction: Optional[discord.Interaction], content: str):
        """|coro|
        Sends a message to the ticket channel or edits an existing interaction response.

        Args:
            interaction (Optional[discord.Interaction]): The interaction object.
            content (str): The content to be sent or used to edit the existing message.
        """

        if interaction:
            await interaction.edit_original_response(content=content)
        else:
            await self.ticket.channel.send(content)

    async def notify_ticket_creator(
            self,
            interaction: Optional[discord.Interaction],
            postscript: str = None,
    ):
        """
        Notifies the ticket creator about the status of their ticket.

        Args:
            interaction (Optional[discord.Interaction]): The interaction associated with the request, if any.
            postscript (Optional[str]): The message sent to the ticket author.
            inactive (bool): Indicates if the ticket is closed due to inactivity.
        """
        if interaction and is_staff(interaction.user, roles=[Roles.ADMIN, Roles.DISCORD_MODERATOR, Roles.MODERATOR]):
            response = f"**Your \"{self.ticket.category.value.lower()}\" ticket has been closed by staff.**"
        elif not self.transcript_file:
            return
        else:
            response = f"**Your \"{self.ticket.category.value.lower()}\" ticket has been closed.**"

        if postscript:
            response += f"\nThis is the message that has been left for you by our team:\n> {postscript}\n"

        if self.transcript_file:
            response += "\n" + "## __Transcript:__"

        with contextlib.suppress(discord.Forbidden):
            if response:
                await self.ticket.creator.send(
                    content=response,
                    file=(
                        discord.File(self.transcript_file)
                        if self.transcript_file
                        else None
                    ),
                )

    def cleanup(self):
        """Cleans up temporary files created during the transcript process."""
        file_paths = (
            [self.transcript_file] + self.zipped_files if self.zipped_files else []
        )
        with contextlib.suppress(FileNotFoundError):
            for file_path in filter(None, file_paths):
                os.remove(file_path)
