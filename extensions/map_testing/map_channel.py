import contextlib
import discord
import logging
import enum
import json
import re
from typing import List, Optional

from extensions.map_testing.submission import InitialSubmission
from extensions.map_testing.checklist import ChecklistView
import extensions.map_testing.embeds as embeds
from constants import Channels, Roles
from utils.text import human_join, sanitize
from utils.changelog import ChangelogPaginator


class MapState(enum.Enum):
    TESTING = ""
    RC = "☑"
    WAITING = "💤"
    READY = "✅"
    DECLINED = "❌"
    RELEASED = "🆙"

    def __str__(self) -> str:
        return self.value


class MapChannel:
    def __init__(self, bot, channel: discord.TextChannel, thread: discord.Thread | None = None):
        self.bot = bot
        self._channel = channel
        self.state = next(
            (s for s in MapState if str(s) == channel.name[0]), MapState.TESTING
        )

        try:
            details, _, self.mapper_mentions, *votes = (channel.topic.splitlines())
            self.votes = votes or []
        except (AttributeError, IndexError):
            raise ValueError("Malformed channel topic") from None

        match = re.match(
            r'^"(?P<name>.+)" by (?P<mappers>.+) \[(?P<server>.+)\]$',
            details.replace("**", ""),
        )
        if match is None:
            raise ValueError("Malformed map details")

        self.name = match["name"]
        self.mappers = re.split(r", | & ", match["mappers"])
        self.server = match["server"]

        self.thread = thread

        self.changelog: Optional[discord.Message] = None
        self.changelog_paginator: Optional[ChangelogPaginator] = None

    @classmethod
    async def create(cls, bot, channel: discord.TextChannel):
        thread = next(iter(channel.threads), None)
        if thread is None:
            async for t in channel.archived_threads():
                thread = t
                break
        if thread is None:
            async for t in channel.archived_threads(private=True):
                thread = t
                break
        if thread and thread.archived:
            try:
                await thread.edit(archived=False)
            except discord.Forbidden:
                logging.warning(f"[MapChannel] No permission to un-archive thread {thread.id} in channel {channel.id}")
            except discord.HTTPException as e:
                logging.warning(f"[MapChannel] Failed to un-archive thread {thread.id}: {e}")
        if thread is None:
            logging.warning(f"[MapChannel] Warning: No thread found in channel {channel.id} ({channel.name})")

        return cls(bot, channel, thread)

    def __repr__(self):
        return json.dumps(
            {
                "MapChannel": {
                    "name": self.name, "state": repr(self.state), "mappers": self.mappers,
                    "mapper_mentions": self.mapper_mentions, "server": self.server, "votes": self.votes,
                    "channel_id": self._channel.id, "channel_name": self._channel.name, "thread": self.thread,
                    "changelog": self.changelog.id if self.changelog is not None else None,
                    "paginator": repr(self.changelog_paginator),
                }
            },
            indent=4,
        )

    def __getattr__(self, attr: str):
        return getattr(self._channel, attr)

    def __str__(self) -> str:
        return str(self.state) + self.emoji + self.filename

    @property
    def filename(self) -> str:
        return sanitize(self.name)

    @property
    def emoji(self) -> str:
        return InitialSubmission.SERVER_TYPES[self.server]

    @property
    def details(self) -> str:
        mappers = human_join([f"**{m}**" for m in self.mappers])
        return f'**"{self.name}"** by {mappers} [{self.server}]'

    @property
    def preview_url(self) -> str:
        return f"https://ddnet.org/testmaps/?map={self.filename}"

    @property
    def _votes(self) -> list:
        return self.votes

    @property
    def _changelog_paginator(self) -> Optional[ChangelogPaginator]:
        return self.changelog_paginator

    @property
    def topic(self) -> str:
        topic = [
            i
            for i in (
                self.details,
                self.preview_url,
                self.mapper_mentions,
                ", ".join(self.votes) if self.votes else None
            )
            if i is not None
        ]
        return "\n".join(topic)

    async def load_changelogs(self):
        with contextlib.suppress(AttributeError):
            await self.setup_changelog_paginator()

    async def setup_changelog_paginator(self):
        """Setup the changelog paginator."""
        self.changelog_paginator = ChangelogPaginator(self.bot, channel=self._channel)
        await self.changelog_paginator.get_data()
        self.changelog = await self.changelog_paginator.assign_changelog_message(self.thread)
        self.bot.add_view(view=self.changelog_paginator, message_id=self.changelog_paginator.changelog.id)

    async def update(
        self, name: str = None, mappers: List[str] = None, server: str = None, mapper_mentions: str = None
    ):
        """|coro|
        Updates the properties of the channel with the provided details.

        Args:
            name (str, optional): The new name for the channel.
            mappers (List[str], optional): A list of mappers associated with the channel.
            server (str, optional): The server type, which must be one of the predefined server types.
            mapper_mentions (str, optional): The user who has submitted the map.
        """
        prev_details = self.details
        prev_mapper_mentions = self.mapper_mentions

        if name is not None:
            self.name = name
        if mappers is not None:
            self.mappers = mappers
        if server is not None:
            server = server.capitalize()
            if server not in InitialSubmission.SERVER_TYPES:
                raise ValueError("Invalid server type")
            self.server = server
        if mapper_mentions is not None:
            self.mapper_mentions = mapper_mentions

        if (prev_details, prev_mapper_mentions) != (self.details, self.mapper_mentions):
            await self.edit(name=str(self), topic=self.topic)

    async def set_state(self, *, state: MapState, set_by: str = None, reset_votes: bool = False):
        """|coro|
        Update the state of the map channel and adjust its properties based on the new state.

        Args:
            state (MapState): The new state to assign to the map channel.
            set_by (str, optional): The identifier of the user who set the state. Defaults to None.
            reset_votes (bool, optional): Indicates whether to reset the channel's votes. Defaults to False.
        """
        self.state = state

        if state is MapState.TESTING or state is MapState.RC:
            category_id = Channels.CAT_TESTING
        elif state is MapState.WAITING:
            category_id = Channels.CAT_WAITING
        else:
            category_id = Channels.CAT_EVALUATED

        options = {"name": str(self)}

        if set_by is not None and set_by not in self.votes:
            self.votes.append(set_by)

        if reset_votes:
            self.reset_votes()

        if category_id != self.category_id:
            options["category"] = category = self.guild.get_channel(category_id)
            options["position"] = (
                category.channels[-1].position + 1
                if state in [MapState.TESTING, MapState.RC]
                else 0
            )

        options["topic"] = f"{self.topic}"
        await self.edit(**options)

    def reset_votes(self):
        self.votes = []

    @classmethod
    async def from_submission(cls, isubm: InitialSubmission, init_state: MapState, thumbnail: discord.File, **options):
        self = cls.__new__(cls)
        self.name = isubm.name
        self.mappers = isubm.mappers
        self.server = isubm.server
        self.state = init_state
        self.mapper_mentions = isubm.author.mention
        self.votes = []
        category_id = None
        if init_state is MapState.TESTING:
            category_id = Channels.CAT_TESTING
        elif init_state is MapState.WAITING:
            category_id = Channels.CAT_WAITING
        if category_id is not None:
            category = isubm.bot.get_channel(category_id)
            self._channel = await category.create_text_channel(
                str(self), topic=self.topic, **options
            )

        # Initial channel setup message
        init_embeds = [embeds.ISubmEmbed(isubm)]
        init_embeds.append(embeds.ISubmErrors()) if self.state == MapState.WAITING else ()
        thumbnail_embed = embeds.ISubmThumbnail(self.preview_url)
        init_embeds.append(thumbnail_embed)
        if thumbnail is not None:
            thumbnail_embed.add_field(name="Thumbnail", value="", inline=False)
            thumbnail_embed.set_image(url=f"attachment://{thumbnail.filename}")

        # Circular import
        from extensions.map_testing.buttons import ButtonLinks, TestingMenu
        await self._channel.send(
            content=f"Mentions: {isubm.author.mention}",
            embeds=init_embeds,
            file=thumbnail,
            view=ButtonLinks()
        )

        # Initial thread setup
        file = await isubm.get_file()
        message = await self._channel.send(file=file)  # This message contains the map file itself
        self.thread = await self._channel.create_thread(name=f"{self.name} — TESTER CONTROLS", message=message)
        
        # Thread Changelog
        self.changelog_paginator = ChangelogPaginator(isubm.bot, channel=self._channel)
        await self.changelog_paginator.add_changelog(
            self._channel,
            isubm.author,
            category="MapTesting/CREATION",
            string=f"Channel for \"{self.name}\" successfully created.",
            map_name=self.name
        )
        await self.changelog_paginator.get_data()

        self.changelog = await self.thread.send(
            embed=self.changelog_paginator.format_changelog_embed(),
            view=self.changelog_paginator,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        await self.changelog_paginator.assign_changelog_message(self.thread)
        
        # Thread checklist
        view = ChecklistView()
        embed = view.generate_checklist_embed()
        await self.thread.send(embed=embed, view=view)
        
        # Thread Tester Controls
        await self.thread.send(
            embed=embeds.TesterControls(),
            view=TestingMenu(isubm.bot),
            allowed_mentions=discord.AllowedMentions(users=False),
        )

        return self, message  # Return the instance instead of a submission
