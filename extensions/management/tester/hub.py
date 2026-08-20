import discord

from utils.hub import HubCog
from extensions.management.tester.views.hub_view import TesterHubView


class TesterHub(HubCog):
    """Keeps the tester hub message alive in Channels.TESTER_HUB (0 keeps
    the hub disabled until the channel exists). The shared upkeep logic
    (HubCog) lives in utils/hub.py; channel cleanup is
    NoChat's job (extensions/management/moderator/no_chat.py)."""

    hub_channel_attr = "TESTER_HUB"

    def build_view(self) -> discord.ui.LayoutView:
        return TesterHubView(self.bot)
