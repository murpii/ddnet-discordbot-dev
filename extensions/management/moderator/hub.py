import discord

from extensions.management.moderator.views.containers.hub import (
    DiscordModHubView,
    ModHubView,
)
from utils.hub import HubCog


class ModHub(HubCog):
    hub_channel_attr = "MOD_HUB"
    hub_marker = "ModHub:"

    def build_view(self) -> discord.ui.LayoutView:
        return ModHubView(self.bot)


class DiscordModHub(HubCog):
    hub_channel_attr = "MOD_HUB"
    hub_marker = "DiscordHub:"

    def build_view(self) -> discord.ui.LayoutView:
        return DiscordModHubView(self.bot)
