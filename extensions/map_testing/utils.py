import io
import discord
from typing import Union, Any, Optional

from extensions.map_testing.embeds import DebugEmbed
from constants import Channels, Roles, Webhooks
from utils.checks import has_map

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extensions.map_testing.map_channel import MapChannel


async def get_unoptimized_map(map_channel: "MapChannel"):
    pins = await map_channel.pins()
    return next(
        (pin for pin in pins if not pin.author.bot and has_map(pin)), None
    )


def by_releases_webhook(message: discord.Message) -> bool:
    return message.webhook_id == Webhooks.DDNET_MAP_RELEASES


def is_testing_channel(channel: discord.TextChannel) -> bool:
    exclude_channels = [
        Channels.TESTING_INFO,
        Channels.TESTING_SUBMIT,
        Channels.TESTER_CHAT,
        Channels.TESTER_VOTES
    ]
    return (
            isinstance(channel, discord.TextChannel)
            and channel.category_id
            in (Channels.CAT_TESTING, Channels.CAT_WAITING, Channels.CAT_EVALUATED)
            and channel.id not in exclude_channels
    )


def is_testing_staff(member: discord.Member) -> bool:
    return any(
        r.id
        in (
            Roles.ADMIN,
            Roles.TESTER,
            Roles.TESTER_EXCL_TOURNAMENTS,
            Roles.TRIAL_TESTER,
            Roles.TRIAL_TESTER_EXCL_TOURNAMENTS,
        )
        for r in member.roles
    )


# TODO: Move this to global utils
async def send_response(
        msg_type: Union[discord.Message, discord.Interaction],
        content: Union[discord.Embed, str],
        file: Optional[discord.File] = None,
) -> None:
    """Sends a response as a Discord message or interaction with optional content and file.

    This function replies to a message or edits/sends a response to an interaction, supporting both embeds and file attachments.

    Args:
        msg_type: The Discord message or interaction to respond to.
        content: The content to send, either as an embed or a string.
        file: An optional file to attach to the response.
    """
    if isinstance(msg_type, discord.message.Message):
        msg = await msg_type.reply(embed=content, mention_author=False)
        if file:
            await msg.reply(file=file, mention_author=False)
    elif isinstance(msg_type, discord.Interaction):
        if file:
            await msg_type.channel.send(content=content, file=file)
            await msg_type.delete_original_response()
        else:
            await msg_type.edit_original_response(content=content)

async def debug_check(subm: Any, msg_type: Union[discord.Message, discord.Interaction], r_event: bool = False) -> bool:
    """Checks the debug output of a submission and sends a formatted response.

    This function sends the debug output for a submission as a message or interaction, formatting it based on its length and context.

    Args:
        subm: The submission object with a debug_map coroutine.
        msg_type: The message or interaction to respond to.
        r_event: Whether the function is being called in response to a ready event.

    Returns:
        bool: True if debug output was sent, False if there was no output.
    """
    debug_output = await subm.debug_map()

    if not debug_output:
        return False

    if isinstance(msg_type, discord.message.Message):
        if len(debug_output) < 1900:
            msg = DebugEmbed(debug_output)
            file = None
        else:
            msg = DebugEmbed()
            file = discord.File(io.StringIO(debug_output), filename="debug_output.txt")  # type: ignore

    if isinstance(msg_type, discord.Interaction):
        msg = "Unable to ready map. Fix the map :lady_beetle:'s first: " if r_event else "Map :lady_beetle: : \n"
        if len(debug_output) < 1900:
            msg = f"{msg}```{debug_output}```"
            file = None
        else:
            msg = f"{msg}Debug output is too long, see attached text file."
            file = discord.File(io.StringIO(debug_output), filename="debug_output.txt")  # noqa

    await send_response(msg_type, msg, file)  # TODO: Return a string/embed/file instead
    return True