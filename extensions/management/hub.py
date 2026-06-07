"""Shared infrastructure for the staff hubs.

A "hub" is one persistent interface message kept alive in a dedicated
channel (Channels.MOD_HUB / Channels.ADMIN_HUB / Channels.TESTER_HUB).
This module holds what the hubs share:

  - staff_guard: the cooldown + role check every hub/log view runs in its
    interaction_check
  - HubButton:  the base class for the hubs' persistent buttons
  - HubCog:     keeps the hub message alive in its channel
"""
import logging
import discord
from discord.ext import commands

from constants import Channels
from utils.checks import is_staff

log = logging.getLogger()


async def staff_guard(
        cooldown: commands.CooldownMapping,
        interaction: discord.Interaction,
        roles: list = None,
) -> bool:
    """Shared button gate: per-user cooldown + staff role check.
    `roles` narrows the allowed role IDs (default: all staff roles)."""
    if cooldown.update_rate_limit(interaction):  # noqa
        await interaction.response.send_message(
            "Hey! Don't spam the buttons.", ephemeral=True
        )
        return False

    if not is_staff(interaction.user, roles=roles):
        await interaction.response.send_message(
            "You're missing the required Role to do that!", ephemeral=True
        )
        return False
    return True


class HubButton(discord.ui.Button):
    """Base for the hubs' persistent buttons / subclasses set label/style/id and implement run()."""

    def __init__(self, bot, *, label: str, custom_id: str,
                 style=discord.ButtonStyle.secondary, roles: list = None):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.bot = bot
        self.roles = roles

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.roles is not None and not is_staff(interaction.user, roles=self.roles):
            await interaction.response.send_message(
                "You're missing the required Role to do that!", ephemeral=True
            )
            return
        await self.run(interaction)

    async def run(self, interaction: discord.Interaction) -> None:
        raise NotImplementedError


def iter_custom_ids(components):
    """Yield every button custom_id in a component tree"""
    for component in components:
        if cid := getattr(component, "custom_id", None):
            yield cid
        if children := getattr(component, "children", None):
            yield from iter_custom_ids(children)


class HubCog(commands.Cog):
    """Base for "hub" cogs: keeps one persistent interface message alive in a dedicated channel

    Subclasses set `hub_channel_attr`
    (the name of the channel constant in constants.Channels; a value of 0 disables the hub) and implement
    `build_view()`. On startup the hub message is edited to the current
    layout if one exists, so view changes deploy without re-posting.

    `hub_marker` lets two hubs share one channel: it is the custom_id prefix
    of this hub's buttons (e.g. "ModHub:" vs "DiscordHub:"), used to recognise
    this hub's own message among the others.
    """

    hub_channel_attr: str = ""
    hub_marker: str = ""

    def __init__(self, bot):
        self.bot = bot
        self.setup = False

    def build_view(self) -> discord.ui.LayoutView:
        raise NotImplementedError

    @property
    def hub_channel_id(self) -> int:
        return getattr(Channels, self.hub_channel_attr, 0) or 0

    def message(self, message) -> bool:
        """Whether `message` is this hub's interface message"""
        if message.author != self.bot.user or not message.components:
            return False
        if not self.hub_marker:
            return True  # only hub in the channel, any components message is ours
        return any(cid.startswith(self.hub_marker) for cid in iter_custom_ids(message.components))

    @commands.Cog.listener()
    async def on_ready(self):
        # on_ready fires again after reconnects
        if self.setup or not self.hub_channel_id:
            return
        self.setup = True

        name = type(self).__name__
        channel = self.bot.get_channel(self.hub_channel_id)
        if channel is None:
            log.warning("%s: channel %d not found, hub disabled", name, self.hub_channel_id)
            return

        async for message in channel.history(limit=50):
            if self.message(message):
                try:
                    await message.edit(view=self.build_view())
                    log.info("%s: refreshed existing hub message %d", name, message.id)
                    return
                except discord.HTTPException:
                    break

        message = await channel.send(view=self.build_view(), allowed_mentions=discord.AllowedMentions.none())
        log.info("%s: posted new hub message %d", name, message.id)
