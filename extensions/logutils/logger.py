import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import DDNet

if not os.path.exists("logs"):
    os.mkdir("logs")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RATELIMIT_PREFIXES = ("We are being rate limited.", "Global rate limit has been hit.",)


def setup_logger(name, level, filename, propagate):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(filename, "a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def is_ratelimit_record(record: logging.LogRecord) -> bool:
    return str(record.msg).startswith(RATELIMIT_PREFIXES)


def code_path() -> str:
    this_file = os.path.abspath(__file__)
    lines = []
    for frame in traceback.extract_stack():
        filename = os.path.abspath(frame.filename)
        if not filename.startswith(PROJECT_ROOT) or "site-packages" in filename:
            continue
        if filename == this_file:
            continue
        relative = os.path.relpath(filename, PROJECT_ROOT)
        lines.append(f"{relative}:{frame.lineno} in {frame.name}")
    return "\n    ".join(lines) or "no bot frames found"


def retry_timestamp(record: logging.LogRecord) -> str:
    # retry_after is the last format arg of both rate limit messages
    try:
        retry_after = float(record.args[-1])
    except (TypeError, ValueError, IndexError):
        return "unknown"
    return (datetime.now() + timedelta(seconds=retry_after)).strftime("%H:%M:%S")


class RatelimitWatcher(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.ratelimit_log = logging.getLogger("ratelimits")

    def filter(self, record: logging.LogRecord) -> bool:
        return is_ratelimit_record(record)

    def emit(self, record: logging.LogRecord) -> None:
        enriched = logging.LogRecord(
            name="ratelimits",
            level=logging.WARNING,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=(
                f"{record.getMessage()}\n"
                f"    retrying at {retry_timestamp(record)}\n"
                f"    {code_path()}"
            ),
            args=None,
            exc_info=None,
        )

        for handler in self.ratelimit_log.handlers:
            handler.handle(enriched)


class DropRatelimitRecords(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name.startswith("discord.") and is_ratelimit_record(record))


def setup_ratelimit_logging():
    http_log = logging.getLogger("discord.http")
    if any(isinstance(handler, RatelimitWatcher) for handler in http_log.handlers):
        return

    setup_logger("ratelimits", logging.WARNING, "logs/ratelimits.log", propagate=False)
    http_log.addHandler(RatelimitWatcher())

    drop = DropRatelimitRecords()
    for handler in logging.getLogger().handlers:
        handler.addFilter(drop)


# root logger (file + console)
setup_logger(None, logging.INFO, "logs/bot.log", propagate=True)
setup_logger("tickets", logging.INFO, "logs/tickets.log", propagate=False)
setup_logger("skin_submits", logging.INFO, "logs/skin_submits.log", propagate=False)
setup_logger("renames", logging.INFO, "logs/renames.log", propagate=False)

logging.getLogger("discord").setLevel(logging.WARNING)

setup_ratelimit_logging()


class Logging(commands.Cog):
    def __init__(self, bot: "DDNet"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, app_command):
        if interaction.guild is None:
            destination = "Private Message"
        else:
            destination = f"#{interaction.channel} ({interaction.guild})"

        options = interaction.data.get("options", [])
        if args := {opt["name"]: opt.get("value") for opt in options}:  # noqa
            logging.info("%s used /%s %s in %s", interaction.user, app_command.name, args, destination)
        else:
            logging.info("%s used /%s in %s", interaction.user, app_command.name, destination)


async def setup(bot: "DDNet"):
    await bot.add_cog(Logging(bot))
