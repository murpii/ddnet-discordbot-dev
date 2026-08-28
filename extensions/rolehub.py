import logging

import discord
from discord.ext import commands

from constants import Roles, Emojis
from utils.containers import INFO_ACCENT, NoticeView, separator
from utils.hub import HubCog

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet

log = logging.getLogger("rolehub")
ROLE_OFFERS = [
    {
        "key": "announcements",
        "label": "Announcements",
        "role_name": "ANNOUNCEMENT_PING",
        "text": "📢 **Announcement Pings**\n-# Get notified when official announcements go out.",
    },
    {
        "key": "testing",
        "label": "Map testing",
        "role_name": "TESTING",
        "text": "🗺️ **Map Testing**\n-# See the map testing channels and help test community maps.",
    },
    {
        "key": "skins",
        "label": "Skins",
        "role_name": "SKIN_SUBMIT_ACCESS",
        "text": "🎨 **Skin Submissions**\n-# See the skin database submission channels.",
    },
    {
        "key": "devcorner",
        "label": "Developer corner",
        "role_name": "DEV_CORNER_ACCESS",
        "text": "💻 **Developer Corner**\n-# See the channels around DDNet development.",
    },
]


def offer_role_id(offer: dict) -> int:
    return int(getattr(Roles, offer["role_name"], 0))


def thin_separator() -> discord.ui.Separator:
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True)  # noqa


class RoleToggleButton(discord.ui.Button):
    def __init__(self, offer: dict, disabled: bool = False):
        super().__init__(
            label="Toggle",
            custom_id=f"rolehub:{offer['key']}",
            style=discord.ButtonStyle.secondary,  # noqa
            disabled=disabled,
        )
        self.offer = offer

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(offer_role_id(self.offer))
        if role is None:
            await interaction.response.send_message(
                view=NoticeView("This role isn't set up yet. Please tell staff."), ephemeral=True
            )
            return

        if role in interaction.user.roles:
            action = interaction.user.remove_roles(role, reason="Role hub")
            note = f"Removed the **{role.name}** role."
        else:
            action = interaction.user.add_roles(role, reason="Role hub")
            note = f"You now have the **{role.name}** role."

        try:
            await action
        except discord.Forbidden:
            log.warning("Role hub can't manage the %s role, check the role hierarchy.", role.name)
            await interaction.response.send_message(
                view=NoticeView("I'm not allowed to manage that role right now. Please tell staff."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(view=NoticeView(note), ephemeral=True)


class RoleHubView(discord.ui.LayoutView):
    def __init__(self, avatar_url: str | None = None):
        super().__init__(timeout=None)
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 2.0, lambda interaction: interaction.user.id
        )

        header_text = discord.ui.TextDisplay(
            f"# <:ddnet:{Emojis.DDNET}> DDNet Role Hub\n"
            "### Make this server yours\n"
            "Pick the channels and pings you actually care about. Every button below is a "
            "toggle, tap it to grab a role and tap it again to let it go, any time you like."
        )
        if avatar_url:
            header = discord.ui.Section(header_text, accessory=discord.ui.Thumbnail(avatar_url))
        else:
            header = header_text

        items = [header, separator()]

        offers = [offer for offer in ROLE_OFFERS if offer_role_id(offer) != 0]
        for index, offer in enumerate(offers):
            role_id = offer_role_id(offer)
            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(offer["text"]),
                    accessory=RoleToggleButton(offer, disabled=role_id < 0),
                )
            )
            if index < len(offers) - 1:
                items.append(thin_separator())

        items.append(separator())
        items.append(discord.ui.TextDisplay("-# Toggle any role on or off whenever you like."))

        self.add_item(discord.ui.Container(*items, accent_colour=INFO_ACCENT))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        retry_after = self.cooldown.get_bucket(interaction).update_rate_limit()
        if retry_after:
            await interaction.response.send_message(
                view=NoticeView("Slow down a little, then try again."), ephemeral=True
            )
            return False
        return True


class RoleHub(HubCog):
    hub_channel_attr = "ROLE_HUB"
    hub_marker = "rolehub:"

    def build_view(self) -> discord.ui.LayoutView:
        avatar_url = self.bot.user.display_avatar.url if self.bot.user else None
        return RoleHubView(avatar_url=avatar_url)


async def setup(bot: "DDNet"):
    if any(offer_role_id(offer) for offer in ROLE_OFFERS):
        bot.add_view(RoleHubView())
    await bot.add_cog(RoleHub(bot))
