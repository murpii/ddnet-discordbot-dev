import discord

from extensions.management.admin.views.hub_view import AdminHubView
from utils.hub import HubCog


class AdminHub(HubCog):
    """Keeps the admin hub message alive in Channels.ADMIN_HUB"""
    hub_channel_attr = "ADMIN_HUB"

    def build_view(self) -> discord.ui.LayoutView:
        return AdminHubView(self.bot)
