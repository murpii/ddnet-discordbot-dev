import re
import logging
from io import BytesIO
from typing import Tuple, Optional

import discord
import requests
from PIL import Image


REGEX = re.compile(r"^\"(?P<skin_name>.+)\" by (?P<user_name>.+) (\((?P<license>.{3,8})\))$", re.IGNORECASE,)
NAME_REGEX = re.compile(r"^[a-zA-Z0-9 _-]+$")


def check_if_has_attachments(message: discord.Message) -> bool:
    return len(message.attachments) > 0


async def has_attachment_dms(message: discord.Message) -> bool:
    if message.attachments and message.attachments[0].filename.endswith(".png"):
        attachment = message.attachments[0]
        image_data = await attachment.read()
        with Image.open(BytesIO(image_data)) as img:
            width, height = img.size
            return (width, height) == (256, 128)
    return False


def check_image_format(message: discord.Message) -> bool:
    return all(
        attachment.content_type == "image/png" for attachment in message.attachments
    )


def check_image_resolution(message: discord.Message) -> Tuple[bool, Optional[str]]:
    has_required = False
    has_optional = False
    for attachment in message.attachments:
        w, h = attachment.width, attachment.height
        if w == 256 and h == 128:
            has_required = True
        elif w == 512 and h == 256:
            has_optional = True
        else:
            err = f"Invalid attachment: {attachment.filename}, Dimensions: {w}x{h}"
            return False, err
    if not has_required:
        return False, "Missing required 256x128 image."
    return True, None


def check_attachment_amount(message: discord.Message) -> bool:
    return len(message.attachments) <= 2


def check_message_structure(message: discord.Message) -> bool:
    return bool(re_match := REGEX.match(message.content))


def check_name_length(message: discord.Message) -> bool:
    re_match = REGEX.match(message.content)
    return len(re_match["skin_name"].encode("utf8")) < 23

def check_dupl_name(message: discord.Message) -> bool:
    re_match = REGEX.match(message.content)
    skin_name = re_match["skin_name"]
    try:
        response = requests.get("https://skins.ddnet.org/skin/skins.json")
        response.raise_for_status()
        skin_data = response.json()
        names_in_use = {skin["name"].lower() for skin in skin_data["skins"]}

        if skin_name.lower() in names_in_use:
            return False
        else:
            return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching skins data: {e}")
        return False


def check_latin_letters(message: discord.Message) -> bool:
    re_match = REGEX.match(message.content)
    skin_name = re_match["skin_name"]
    return bool(NAME_REGEX.match(skin_name))


def check_license(message: discord.Message) -> bool:
        re_match = REGEX.match(message.content)
        return re_match["license"] in [
            "CC0",
            "CC BY",
            "CC BY-SA",
        ]
