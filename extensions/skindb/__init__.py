import asyncio
import contextlib
import logging
from io import BytesIO

import discord
from discord import RawMessageUpdateEvent
from discord.ext import commands
from PIL import Image

from .checks import (
    check_message_structure,
    check_license,
    check_if_has_attachments,
    check_attachment_amount,
    check_dupl_name, check_name_length, check_latin_letters,
    check_image_format,
    check_image_resolution,
    has_attachment_dms
)

from constants import Guilds, Channels, Roles, Emojis
from utils.image import skin_renderer

log = logging.getLogger("skin_submits")


ERROR_MAP = {
    "check_if_has_attachments": (
        "- Your submission is missing attachments. Attach all skins to your submission message.",
        "Missing attachments",
    ),
    "check_image_format": (
        "- Wrong image format. Only PNGs are allowed.",
        "Incorrect image format",
    ),
    "check_image_resolution": (
        "- One of the attached skins does not have the correct image resolution. Resolution must be 256x128, "
        "and if possible provide a 512x256 along with the 256x128",
        "Bad image resolution",
    ),
    "check_attachment_amount": (
        "- Only 2 attachments per submission. Don't attach any additional images or gifs, please.",
        "Exceeded attachment limit",
    ),
    "check_message_structure": (
        "- Your message isn't properly formatted. Follow the message structure written in <#{Channels.SKIN_INFO}>. "
        "Also keep in mind licenses are now required for every submission.",
        "Bad message structure",
    ),
    "license_missing_or_invalid": (
        "- Bad License. Possible licenses: `(CC0)`, `(CC BY)` or `(CC BY-SA)`\n"
        "```md\n"
        "# Recommended License Types\n"
        "CC0 - skin is common property, everyone can use/edit/share it however they like\n"
        "CC BY - skin can be used/edited/shared, but must be credited\n"
        "CC BY-SA - skin can be used/edited/shared, but must be credited and "
        "derived works must also be shared under the same license```",
        "License Missing or invalid",
    ),
    "skin_name_latin_letters_only": (
        "The skin name should contain only Latin letters (A-Z, a-z), numbers (0-9), spaces, underscores (_), "
        "and hyphens (-). Other special characters or non-Latin characters are not allowed.",
        "Skin name must contain only Latin letters, numbers, spaces, underscores, or hyphens",
    ),
    "skin_name_taken": (
        "The skin name you provided is already in use. Please choose a different name.",
        "Skin name is already taken",
    ),
}


async def send_to_renderer(message):
    attachments = message.attachments
    images = [
        Image.open(BytesIO(await attachment.read())) for attachment in attachments
    ]
    image_to_process = next((img for img in images if img.size == (256, 128)), None)
    processed_images = skin_renderer(image_to_process)
    final_image = Image.new("RGBA", (512, 64))
    x_offset = y_offset = 0
    for name, processed_img in processed_images.items():
        final_image.paste(processed_img, (x_offset, y_offset))
        x_offset += processed_img.size[0]
        if x_offset >= final_image.size[0]:
            x_offset = 0
            y_offset += processed_img.size[1]
    buf = BytesIO()
    final_image.save(buf, "PNG")
    buf.seek(0)
    return discord.File(buf, filename="final_image.png")


def is_staff(member: discord.Member) -> bool:
    return any(
        r.id in (Roles.DISCORD_MODERATOR, Roles.SKIN_DB_CREW)
        for r in member.roles
    )


class SkinDB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # im using a dict to store all message ids for now

    async def send_error_messages(self, message: discord.Message, error_messages: list) -> bool:
        try:
            error_messages.insert(0, "Skin Submit Errors: ")
            await message.author.send("\n".join(error_messages))
        except discord.Forbidden:
            logging.info(
                f"Skin submit: Unable to DM {message.author} due to their privacy settings."
            )
            privacy_err = (
                f"Skin submission failed. Unable to DM {message.author.mention}. "
                f"Change your privacy settings to allow direct messages from this server."
            )
            privacy_err_msg = await message.channel.send(content=privacy_err)
            await asyncio.sleep(2 * 60)
            await privacy_err_msg.delete()
        return False

    async def checks(self, message: discord.Message) -> bool | discord.File:
        error_messages = []
        log_errors = []

        if not check_message_structure(message):
            error_messages.append(ERROR_MAP["check_message_structure"][0].format(Channels=Channels))  # noqa
            log_errors.append(ERROR_MAP["check_message_structure"][1])
        else:
            conditions = [
                (check_if_has_attachments, "check_if_has_attachments"),
                (check_image_format, "check_image_format"),
                (check_image_resolution, "check_image_resolution"),
                (check_attachment_amount, "check_attachment_amount"),
                (check_name_length, "skin_name_too_long"),
                (check_latin_letters, "skin_name_latin_letters_only"),
                (check_dupl_name, "skin_name_taken"),
                (check_license, "license_missing_or_invalid")
            ]

            for check_func, error_mapping_key in conditions:
                if check_func == check_image_resolution:
                    is_valid, dim = check_image_resolution(message)
                    if not is_valid:
                        error_messages.append(f"{ERROR_MAP[error_mapping_key][0]}\n`{dim}`")
                        log_errors.append(ERROR_MAP[error_mapping_key][1])
                elif not check_func(message):
                    error_messages.append(ERROR_MAP[error_mapping_key][0].format(Channels=Channels))  # noqa
                    log_errors.append(ERROR_MAP[error_mapping_key][1])

        if not error_messages:
            return await send_to_renderer(message)

        log_error_message = (
            f'Skin submit errors by {message.author}: '
            f'{", ".join(log_errors)}\n'
            f'Message content:\n'
            f'{message.content}'
        )

        embed = discord.Embed(
            title=f"Skin Submission Errors by {message.author}",
            description="The following errors occurred during the skin submission process.",
            color=discord.Color.red(),
        )
        for error in error_messages:
            embed.add_field(name="Error", value=error, inline=False)
        if message.content:
            embed.add_field(
                name="Message Content:",
                value=f"```prolog\n{message.content}```",
                inline=False
            )
        embed.set_footer(text=f"Skin submission log | Author ID: {message.author.id}")
        embed.timestamp = discord.utils.utcnow()

        logs = self.bot.get_channel(Channels.SKIN_LOGS)

        with contextlib.suppress(discord.HTTPException):
            await logs.send(embed=embed)
        log.info(log_error_message)
        return await self.send_error_messages(message, error_messages)

    @commands.Cog.listener("on_message")
    async def run_checks(self, message: discord.Message):
        if isinstance(message.channel, discord.DMChannel) and await has_attachment_dms(message):
            render = await send_to_renderer(message)
            await message.channel.send(file=render)
            return

        if (
            message.channel.id != Channels.SKIN_SUBMIT
            or message.author.bot
            or is_staff(message.author)
        ):
            return

        file = await self.checks(message)
        if file:
            image_preview_message = await message.channel.send(file=file)
            self.cache[message.id] = image_preview_message.id
            await image_preview_message.add_reaction(self.bot.get_emoji(Emojis.BROWNBEAR))
            await asyncio.sleep(1) # Ratelimit
            await image_preview_message.add_reaction(self.bot.get_emoji(Emojis.CAMMOSTRIPES))
        else:
            await message.delete()

    @commands.Cog.listener("on_message_delete")
    async def message_delete_handler(self, message: discord.Message):
        if message.id in self.cache:
            preview_message_id = self.cache[message.id]
            preview_message = await message.channel.fetch_message(preview_message_id)
            await preview_message.delete()
            del self.cache[message.id]

    @commands.Cog.listener("on_raw_message_edit")
    async def raw_message_edit_handler(self, payload: RawMessageUpdateEvent):
        """
        Handles the event when a submission is edited in the skin submit channel.
        """
        channel = self.bot.get_channel(payload.channel_id)

        if not channel:
            return

        if (
            channel.guild is None
            or channel.guild.id != Guilds.DDNET
            or channel.id != Channels.SKIN_SUBMIT
        ):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound or discord.Forbidden:
            return

        if (
                message.author.bot
                or is_staff(message.author)
        ):
            return

        if not await self.checks(message):
            await message.add_reaction("❌")
        else:
            for reaction in message.reactions:
                if str(reaction.emoji) == "❌":
                    async for user in reaction.users():
                        await message.remove_reaction("❌", user)
                        await asyncio.sleep(1)  # Ratelimit


async def setup(bot: commands.Bot):
    await bot.add_cog(SkinDB(bot))
