import contextlib
import json
import logging
import os

import discord

from constants import Channels
from utils.checks import forbidden_report, missing_permissions, permission_report
from utils.containers import markup_kwargs
from utils.text import render_constants

log = logging.getLogger()

TEMPLATE_DIR = "data/templates"
SECTION_DIR = os.path.join(TEMPLATE_DIR, "sections")
GRAPHICS_DIR = "data/assets/graphics"


def load_manifest() -> dict:
    with open(os.path.join(TEMPLATE_DIR, "manifest.json"), encoding="utf-8") as file:
        return json.load(file)


def section_names() -> list:
    """All section names in manifest order, each paired with the template
    it belongs to: [(section, template), ...]"""
    names = []
    for template_name, template in load_manifest().items():
        for message in template["messages"]:
            names.extend(
                (section, template_name)
                for section in message.get("sections", [])
            )
    return names


def section_path(section: str) -> str:
    if section not in [name for name, _ in section_names()]:
        raise ValueError(f"Unknown template section: {section}")
    return os.path.join(SECTION_DIR, f"{section}.md")


def read_section(section: str) -> str:
    with open(section_path(section), encoding="utf-8") as file:
        return file.read().strip("\n")


def save_section(section: str, text: str) -> None:
    with open(section_path(section), "w", encoding="utf-8", newline="\n") as file:
        file.write(text.strip("\n") + "\n")


render = render_constants


@contextlib.asynccontextmanager
async def hide_during_rebuild(channel):
    """
    Hide the channel from @everyone for the duration of the rebuild, so the
    purge + re-send flurry isn't visible
    """
    everyone = channel.guild.default_role
    original = channel.overwrites_for(everyone)
    hidden = False

    try:
        overwrite = channel.overwrites_for(everyone)
        overwrite.view_channel = False
        await channel.set_permissions(everyone, overwrite=overwrite, reason="Template rebuild: hiding")
        hidden = True
    except discord.Forbidden:
        log.warning(
            "send_template: can't hide %s (needs manage_roles); rebuilding visibly", channel
        )

    try:
        yield
    finally:
        if hidden:
            with contextlib.suppress(discord.HTTPException):
                await channel.set_permissions(
                    everyone,
                    overwrite=None if original.is_empty() else original,
                    reason="Template rebuild: restoring visibility",
                )


def rebuild_permissions() -> tuple:
    """What the bot needs in a channel to rebuild a template there.

    manage_roles is not in here, hiding the channel during the rebuild is
    optional and hide_during_rebuild() already copes without it.
    """
    return (
        "view_channel",
        "send_messages",
        "read_message_history",
        "manage_messages",
        "embed_links",
        "attach_files",
        "add_reactions",
    )


async def send_template(bot, name: str) -> str:
    """
    Hides the templates channel, purges and resends all of its messages,
    then restores the channels previous visibility.
    """
    template = load_manifest()[name]
    channel_id = getattr(Channels, template["channel"], 0)
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

    needed = rebuild_permissions()
    if missing_permissions(channel, *needed):
        # bail out before purging, a half-rebuilt channel is worse than none
        return f"Can't rebuild '{name}'.\n{permission_report(channel, *needed)}"

    sent = 0
    last_message = None
    try:
        async with hide_during_rebuild(channel):
            await channel.purge()

            for message in template["messages"]:
                if image := message.get("image"):
                    path = os.path.join(GRAPHICS_DIR, image)
                    last_message = await channel.send(file=discord.File(path, filename=image))
                    sent += 1

                for section in message.get("sections", []):
                    # mentions render properly but never ping anyone
                    last_message = await channel.send(
                        **markup_kwargs(render(read_section(section))),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    sent += 1

            if template.get("end_reaction") and last_message:
                await last_message.add_reaction(template["end_reaction"])
    except discord.Forbidden as error:
        return (
            f"Rebuild of '{name}' stopped after {sent} messages: {error.text}\n"
            f"{forbidden_report(error, channel)}"
        )

    return f"Rebuilt <#{channel_id}>: {sent} messages."
