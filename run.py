import asyncio
import logging
import platform
import time
import sys
from configparser import ConfigParser
from typing import Optional
import traceback

import aiohttp
from requests_cache import CachedSession
import asyncmy
import discord
from discord import Intents
from discord.ext import commands
from colorama import Back, Fore, Style

from constants import Guilds
from extensions.ticketsystem.manager import TicketManager
from extensions.player_finder.manager import PlayerfinderManager
from extensions.moderator.manager import ModeratorDB
from extensions.help import HelpCommand

config = ConfigParser()
config.read("config.ini")

discord.voice_client.VoiceClient.warn_nacl = False
log = logging.getLogger()

extensions = [
    ("extensions.logutils.logger", True),
    ("extensions.logutils.errorhandler", True),
    ("extensions.admin", True),
    ("extensions.admin.rename", True),
    ("extensions.assignees", True),
    ("extensions.moderator", True),
    ("extensions.map_testing", True),
    ("extensions.map_testing.secret_testing", True),
    ("extensions.map_testing.bans", True),
    ("extensions.skindb", True),
    ("extensions.player_finder", True),
    ("extensions.player_finder.secret", True),
    ("extensions.ticketsystem", True),
    ("extensions.wiki.wiki", True),
    # ("extensions.wiki.wiki2", True),
    ("extensions.misc.meme", True),
    ("extensions.misc.misc", True),
    ("extensions.misc.profile", True),
    ("extensions.misc.status", True),
    ("extensions.misc.guides", True),
    ("extensions.chat.github", True),
    ("extensions.chat.forum", True),
    # ("extensions.chat.templates", True),
    # ("extensions.chat.auto_responses", True),
    # ("extensions.events.map_awards", True),
    # ("extensions.events.teeguesser", False),
    ("extensions.events", True),
    # ("extensions.events", True),
    ("extensions.testing", True),
    ("extensions.debug", True)
]


class DDNet(commands.Bot):
    """Represents the DDNet Discord bot.

    This class extends the `commands.Bot` to provide additional functionality specific to the DDNet community.
    It initializes various components such as the database connection pool, session management and caching.

    Attributes:
        pool: The database connection pool used for database operations.
        config: Configuration settings for the bot.
        session: The current session for managing user interactions.
        ticket_manager: An instance of the TicketManager for handling tickets.
        pfm: An instance of the PlayerfinderManager for managing player-related queries.
        request_cache: A cached session for storing requests.
        session_manager: An instance of the SessionManager for managing sessions.
        synced: A flag indicating whether the bot's commands have been synced.
    """

    def __init__(self, **kwargs):
        super().__init__(
            command_prefix="$",
            fetch_offline_members=True,
            help_command=HelpCommand(),
            intents=Intents().all(),
        )

        self.pool = kwargs.pop("pool")
        self.config = kwargs.pop("config")
        self.session = None
        self.ticket_manager = TicketManager(self)
        self.pfm = PlayerfinderManager(self)
        self.moddb = ModeratorDB(self)
        self.request_cache = CachedSession(
            cache_name="data/cache", backend="sqlite", expire_after=60 * 60 * 2
        )
        self.session_manager = SessionManager()
        self.synced = False

    async def close(self):
        """Closes the bot and releases all resources."""

        log.info("Closing")
        self.request_cache.close()
        for session in self.session_manager.sessions.values():
            await session.close()
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()
        await super().close()

    async def fetch(self, query, *args, fetchall=False) -> tuple:
        """|coro|
        Executes an SQL query and retrieves the results from the database.

        Args:
            query (str): The SQL query to be executed.
            *args: The arguments to be passed to the SQL query.
            fetchall (bool): A flag indicating whether to fetch all results (True) or just one (False).

        Returns:
            tuple: A tuple containing the fetched results,
            which can be a single row or multiple rows depending on the `fetchall` parameter.
        """

        async with self.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, args)
                return await cursor.fetchall() if fetchall else await cursor.fetchone()

    async def upsert(self, query, *args) -> int:
        """|coro|
        Executes an SQL query and commits the changes to the database.

        Args:
            query (str): The SQL query to be executed.
            *args: The arguments to be passed to the SQL query.

        Returns:
            int: The number of rows affected by the query (rowcount).
        """

        async with self.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, args)
                await connection.commit()
                rowcount = cursor.rowcount
            return rowcount

    async def setup_hook(self):
        """|coro|
        Initializes the bot by loading extensions and setting up the database connection.

        This function iterates through the extensions,
        loading each one that is marked for initialization.
        It also checks the status of the database connection pool and retrieves a session for the bot's operations
        """

        for cog, init in extensions:
            if init:
                try:
                    await self.load_extension(cog)
                    log.info(f"Successfully loaded {cog}")
                except Exception:
                    logging.error("Failed to load extension:\n%s", traceback.format_exc())

        log.info(f"Python version: {sys.version}")
        log.info(f"Discord.py version: {discord.__version__}")

        if self.pool is None:
            await self.close()
            return
        else:
            log.info("Database pool created successfully.")

        self.session = await self.session_manager.get_session(self.__class__.__name__)

    async def on_ready(self):
        await self.wait_until_ready()
        # Using colorama here, so ANSI escape character sequences work under MS Windows
        prefix = (
                Back.RESET
                + Fore.GREEN
                + time.strftime("%H:%M:%S UTC", time.gmtime())
                + Back.RESET
                + Fore.WHITE
                + Style.BRIGHT
        )
        print(f"{prefix} Logged in as {Fore.YELLOW}{self.user.name}")
        print(f"{prefix} Bot ID {Fore.YELLOW}{str(self.user.id)}")
        print(f"{prefix} Discord.py Version {Fore.YELLOW}{discord.__version__}")
        print(f"{prefix} Python Version {Fore.YELLOW}{str(platform.python_version())}")

        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="DDNet")
        )

        # on_ready is called multiple times and syncing is heavily rate-limited
        # so a check here should hopefully ensure this only happens once
        if not self.synced:
            synced_global = await self.tree.sync()
            # Commands useful only on the DDNet discord server (i.e: map testing related commands)
            synced_guild = await self.tree.sync(guild=discord.Object(Guilds.DDNET))

            self.synced = True
            log.info(
                f"Slash CMDs Synced - Global: {len(synced_global)}, Guild: {len(synced_guild)}"
            )

    # This is kinda useless as we reload the bot daily. The message cache gets cleared with every reload.
    def get_message(self, message_id: int) -> Optional[discord.Message]:
        return discord.utils.get(self.cached_messages, id=message_id)

    @staticmethod
    async def reply(message: discord.Message, content: Optional[str] = None, **kwargs) -> discord.Message:
        reference = message if message.reference is None else message.reference
        if isinstance(reference, discord.MessageReference):
            reference.fail_if_not_exists = False
        return await message.channel.send(content, reference=reference, **kwargs)

    async def get_or_fetch_member(self, *, guild: discord.Guild, user_id: int) -> discord.Member | discord.User | None:
        try:
            return guild.get_member(user_id) or await guild.fetch_member(user_id)
        except discord.NotFound:
            try:
                return await self.fetch_user(user_id)
            except discord.NotFound:
                return None


class SessionManager:
    """Manages HTTP sessions for different components of the bot.

    Attributes:
        sessions (dict): A dictionary that stores active sessions keyed by cog names.

    Methods:
        get_session(cog_name): Retrieves an existing session or creates a new one for the specified cog.
        Close_session(cog_name): Closes and removes the session associated with the specified cog.
    """

    def __init__(self):
        self.sessions = {}

    def __repr__(self):
        return f"{self.sessions}"

    async def get_session(self, cog_name):
        if cog_name not in self.sessions:
            self.sessions[cog_name] = aiohttp.ClientSession()
        return self.sessions[cog_name]

    async def close_session(self, cog_name):
        if cog_name in self.sessions:
            await self.sessions[cog_name].close()
            del self.sessions[cog_name]


async def main():
    try:
        pool = await asyncmy.create_pool(
            user=config["DATABASE"]["MARIADB_USER"],
            password=config["DATABASE"]["MARIADB_PASSWORD"],
            db=config["DATABASE"]["MARIADB_DB"],
            host=config["DATABASE"]["MARIADB_HOST"],
            port=int(config["DATABASE"]["MARIADB_PORT"]),
            init_command="SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED",
            maxsize=10,
            pool_recycle=3600,
        )
    except Exception as e:
        log.critical("Failed to connect to MariaDB: %s", e)
        return None

    async with aiohttp.ClientSession() as session:
        client = DDNet(config=config, session=session, pool=pool)
        await client.start(config.get("AUTH", "TOKEN_DISCORD"), reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped via keyboard interrupt")
