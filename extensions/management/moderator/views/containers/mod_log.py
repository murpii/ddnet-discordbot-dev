import re
from typing import Optional

import discord
from discord.ext import commands

from utils.text import to_discord_timestamp
from utils.containers import ALERT_ACCENT, separator
from extensions.management.hub import staff_guard

MENTION_RE = re.compile(r"<@!?(\d+)>")


def find_first_mention_id(message: discord.Message) -> Optional[int]:
    for embed in message.embeds:
        if embed.description and (match := MENTION_RE.search(embed.description)):
            return int(match[1])

    def walk(components) -> Optional[int]:
        for component in components:
            content = getattr(component, "content", None)
            if content and (match := MENTION_RE.search(content)):
                return int(match[1])
            found = walk(getattr(component, "children", None) or [])
            if found is not None:
                return found
        return None

    return walk(message.components)


async def open_user_info_panel(bot, interaction: discord.Interaction) -> None:
    user_id = find_first_mention_id(interaction.message)
    if user_id is None:
        await interaction.response.send_message(
            "Could not find a user in this log entry.", ephemeral=True
        )
        return

    target = await bot.get_or_fetch_member(guild=interaction.guild, user_id=user_id)
    info = await bot.moddb.fetch_user_info(target) if target else None

    from extensions.management.moderator.views.containers.user_info import UserInfoView, NoUserInfoView
    if not info:
        await interaction.response.send_message(view=NoUserInfoView(), ephemeral=True)
        return

    await interaction.response.send_message(
        view=UserInfoView(bot, info, interaction.user), ephemeral=True
    )


class ModLogInfoButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(
            label="User Info",
            style=discord.ButtonStyle.green,  # noqa
            custom_id="ModLog:info",
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_user_info_panel(self.bot, interaction)


class ModLogView(discord.ui.LayoutView):
    def __init__(self, bot, text: str = "-# Moderation log entry", thumbnail_url: str = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, lambda i: i.user.id
        )

        header = "## ⚔️ Discord Moderation"
        if thumbnail_url:
            entry = discord.ui.Section(
                header,
                text,
                accessory=discord.ui.Thumbnail(thumbnail_url),
            )
        else:
            entry = discord.ui.TextDisplay(f"{header}\n{text}")

        footer = discord.ui.TextDisplay(f"-# {to_discord_timestamp(discord.utils.utcnow(), 'f')}")

        self.add_item(
            discord.ui.Container(
                entry,
                separator(),
                discord.ui.ActionRow(ModLogInfoButton(bot)),
                separator(),
                footer,
                accent_colour=ALERT_ACCENT,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await staff_guard(self.cooldown, interaction, roles="mods")
