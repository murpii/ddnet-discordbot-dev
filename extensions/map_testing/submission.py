import contextlib
import enum
import logging
import os
import re
import io
from io import BytesIO
from typing import Optional

import discord

from . import map_visualize_size
from extensions.map_testing.map_states import MapState
from utils.misc import run_process_shell, run_process_exec, check_os
from utils.text import sanitize

log = logging.getLogger("mt")


class SubmissionState(enum.Enum):
    PENDING = "⏳"
    VALIDATED = "☑️"
    UPLOADED = "🆙"
    PROCESSED = "✅"
    ERROR = "❌"

    def __str__(self) -> str:
        return self.value


class Submission:
    __slots__ = ("message", "author", "channel", "filename", "_bytes", "_state")

    DIR = "data/map-testing"

    def __init__(self, message: discord.Message, *, raw_bytes: Optional[bytes] = None):
        self.message = message
        self.author = message.author
        self.channel = message.channel

        for attachment in message.attachments:
            if attachment.filename.endswith(".map"):
                self.filename = attachment.filename
                break

        self._bytes = raw_bytes
        self._state = SubmissionState.PENDING

    def __str__(self) -> str:
        return self.filename[:-4]

    @property
    def state(self) -> SubmissionState:
        return self._state

    async def buffer(self) -> BytesIO:
        if self._bytes is None:
            map_attachment = next(
                (
                    attachment
                    for attachment in self.message.attachments
                    if attachment.filename.endswith(".map")
                ),
                None,
            )

            if map_attachment is not None:
                self._bytes = await map_attachment.read()
            else:
                raise ValueError("No .map file found in message attachments")
        return BytesIO(self._bytes)

    async def get_file(self) -> discord.File:
        return discord.File(await self.buffer(), filename=self.filename)

    async def set_state(self, status: SubmissionState):
        self._state = status
        for reaction in self.message.reactions:
            if any(str(s) == str(reaction) for s in SubmissionState):
                await self.message.clear_reaction(reaction)

        await self.message.add_reaction(str(status))

    # What's the point of this method?
    async def pin(self):
        if self.message.pinned:
            return
        await self.message.pin()

    async def visualize_size(self) -> discord.File:
        buf = await self.buffer()
        out_buf = map_visualize_size.visualize_from_bytes(buf.getvalue())
        file = discord.File(out_buf, filename=f"FileSizeStats.png")
        return file

    async def debug_map(self) -> Optional[str]:
        _, ext = check_os()
        tmp = f"{self.DIR}/tmp/{self.message.id}.map"

        buf = await self.buffer()
        with open(tmp, "wb") as f:
            f.write(buf.getvalue())

        try:
            dbg_stdout, dbg_stderr = await run_process_exec(
                f'{self.DIR}/twmap-check{ext}',
                "-vv", "--", tmp)
        except RuntimeError as exc:
            ddnet_dbg_error = str(exc)
            return log.error(
                "Debugging failed of map %r (%d): %s",
                self.filename,
                self.message.id,
                ddnet_dbg_error,
            )

        output = dbg_stdout + dbg_stderr
        ddnet_dbg_stdout, ddnet_dbg_stderr = None, None

        try:
            ddnet_dbg_stdout, ddnet_dbg_stderr = await run_process_exec(
                f'{self.DIR}/twmap-check-ddnet{ext}',
                "--omit-unreliable-checks", "--", tmp)
        except RuntimeError as exc:
            ddnet_dbg_error = str(exc)
            log.error(
                "DDNet checks failed of map %r (%d): %s",
                self.filename,
                self.message.id,
                ddnet_dbg_error,
            )
        if not ddnet_dbg_stderr:
            output += ddnet_dbg_stdout

        # cleanup
        os.remove(tmp)

        return output

    async def edit_map(self, *args: str) -> (str, Optional[discord.File]):
        if "--mapdir" in args:
            return "Can't save as MapDir using the discord bot", None

        tmp = f"{self.DIR}/tmp/{self.message.id}.map"
        edited_tmp = f"{tmp}_edit"

        buf = await self.buffer()
        with open(tmp, "wb") as f:
            f.write(buf.getvalue())

        _, ext = check_os()

        try:
            executable = f"{self.DIR}/twmap-edit{ext}"
            stdout, stderr = await run_process_exec(executable, tmp, edited_tmp, *args)
        except RuntimeError as exc:
            error = str(exc)
        else:
            error = stderr

        if error:
            log.error(
                "Editing failed of map %r (%d): %s",
                self.filename,
                self.message.id,
                error
            )
            raise RuntimeError(error)

        if os.path.exists(edited_tmp):
            with open(edited_tmp, "rb") as f:
                file = discord.File(BytesIO(f.read()), filename=f"{str(self)}.map")
            os.remove(edited_tmp)
        else:
            file = None

        os.remove(tmp)
        return stdout, file


class InitialSubmission(Submission):
    __slots__ = Submission.__slots__ + ("bot", "name", "mappers", "server", "map_channel", "thumbnail")

    _FORMAT_RE = r"^\"(?P<name>.+)\" +by +(?P<mappers>.+) +\[(?P<server>.+)\]$"

    SERVER_TYPES = {
        "Novice": "👶",
        "Moderate": "🌸",
        "Brutal": "💪",
        "Insane": "💀",
        "Dummy": "♿",
        "Oldschool": "👴",
        "Solo": "⚡",
        "Race": "🏁",
        "Fun": "🎉",
    }

    def __init__(self, bot, message: discord.Message, *, raw_bytes: Optional[bytes] = None):
        super().__init__(message, raw_bytes=raw_bytes)

        self.bot = bot
        self.name = None
        self.mappers = None
        self.server = None
        self.thumbnail = None
        self.map_channel = None

    def validate(self):
        # can't do this in init since we need a reference to the submission even if it's improper
        match = re.search(self._FORMAT_RE, self.message.content, flags=re.IGNORECASE)
        if match is None:
            raise ValueError(
                "Your map submission doesn't contain correctly formated details"
            )

        self.name = match["name"]
        if sanitize(self.name) != str(self):
            raise ValueError("Name and filename of your map submission don't match")

        self.mappers = re.split(r", | , | & | and ", match["mappers"])

        self.server = match["server"].capitalize()
        if self.server not in self.SERVER_TYPES:
            raise ValueError("The server type of your map submission is not valid")

    async def respond(self, error: Exception):
        with contextlib.suppress(discord.Forbidden):
            await self.author.send(error)

    @property
    def emoji(self) -> str:
        return self.SERVER_TYPES.get(self.server, "")

    async def generate_thumbnail(self) -> discord.File:
        tmp = f'{self.DIR}/tmp/{self.message.id}.map'

        buf = await self.buffer()
        with open(tmp, 'wb') as f:
            f.write(buf.getvalue())

        _, ext = check_os()
        cmd = [f"{self.DIR}/twgpu-map-photography"]
        if ext:
            cmd[0] += ext
        cmd.append(tmp)

        stdout, stderr = await run_process_shell(' '.join(cmd))

        try:
            stdout, stderr = await run_process_shell(' '.join(cmd))
        except Exception as e:
            log.error(e)
            raise RuntimeError(e) from e
        else:
            log.info("stdout: %s", stdout)
            if stderr:
                if "XDG_RUNTIME_DIR is invalid or not set" in stderr:
                    log.warning("Ignoring harmless stderr: %s", stderr)
                else:
                    log.error("stderr: %s", stderr)
                    raise RuntimeError(stderr)

        try:
            with open(f'{self.message.id}.png', 'rb') as f:
                buf = BytesIO(f.read())
        except FileNotFoundError as error:
            log.info(error)

        # cleanup
        os.remove(tmp)
        os.remove(f'{self.message.id}.png')

        return discord.File(buf, filename=f'{self}.png')

    async def process(self) -> Submission:
        perms = discord.PermissionOverwrite(read_messages=True)
        users = [self.message.author]
        for reaction in self.message.reactions:
            users += [u async for u in reaction.users()]
        overwrites = {u: perms for u in users}
        overwrites |= self.channel.category.overwrites

        # category permissions:
        # - @everyone:  read_messages=False
        # - Tester:     manage_channels=True, read_messages=True, manage_messages=True, manage_roles=True
        # - testing:    read_messages=True
        # - bot.user:   read_messages=True, manage_messages=True

        # circular imports
        from extensions.map_testing.map_channel import MapChannel

        debug_output = await self.debug_map()
        state = MapState.WAITING if debug_output else MapState.TESTING
        self.map_channel, message = await MapChannel.from_submission(self, state, overwrites=overwrites)

        # DEBUG Map: Runs twmap-check-ddnet on the isubm map file
        if debug_output:
            if len(debug_output) < 1900:
                await message.reply(
                    f"Map 🐞:\n```{debug_output}```",
                    mention_author=False
                )
            else:
                file = discord.File(io.StringIO(debug_output), filename="debug_output.txt")  # noqa
                await message.reply(
                    f"Map 🐞:\n"
                    f"Debug output is too long, see attached file.",
                    file=file,
                    mention_author=False
                )
        else:
            await message.add_reaction("👌")

        return Submission(message, raw_bytes=self._bytes)
