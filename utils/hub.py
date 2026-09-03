import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from constants import Channels

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger(__name__)


def iter_custom_ids(components):
    for component in components:
        if cid := getattr(component, "custom_id", None):
            yield cid
        if children := getattr(component, "children", None):
            yield from iter_custom_ids(children)
        if accessory := getattr(component, "accessory", None):
            yield from iter_custom_ids([accessory])


class HubCog(commands.Cog):
    hub_channel_attr: str = ""
    hub_marker: str = ""

    def __init__(self, bot: "DDNet"):
        self.bot = bot
        self.setup = False
        self.hub_message = None

    def build_view(self) -> discord.ui.LayoutView:
        raise NotImplementedError

    async def hub_ready(self) -> None:
        """Hook called after the hub message is posted or refreshed, override for post-setup."""

    @property
    def hub_channel_id(self) -> int:
        return getattr(Channels, self.hub_channel_attr, 0) or 0

    def message(self, message) -> bool:
        if message.author != self.bot.user or not message.components:
            return False
        if not self.hub_marker:
            return True
        return any(cid.startswith(self.hub_marker) for cid in iter_custom_ids(message.components))

    @commands.Cog.listener()
    async def on_ready(self):
        if self.setup or not self.hub_channel_id:
            return
        self.setup = True

        name = type(self).__name__
        channel = self.bot.get_channel(self.hub_channel_id)
        if channel is None:
            log.warning("%s: channel %d not found, hub disabled", name, self.hub_channel_id)
            return

        keep = None
        async for message in channel.history(limit=50):
            if not self.message(message):
                continue
            if keep is None:
                keep = message
                continue

            if self.hub_marker:
                with contextlib.suppress(discord.HTTPException):
                    await message.delete()
                    log.info("%s: deleted stale duplicate hub message %d", name, message.id)

        if keep is not None:
            try:
                await keep.edit(view=self.build_view(), allowed_mentions=discord.AllowedMentions.none())
                self.hub_message = keep
                log.info("%s: refreshed existing hub message %d", name, keep.id)
                await self.hub_ready()
                return
            except discord.HTTPException:
                pass

        self.hub_message = await channel.send(
            view=self.build_view(), allowed_mentions=discord.AllowedMentions.none()
        )
        log.info("%s: posted new hub message %d", name, self.hub_message.id)
        await self.hub_ready()
