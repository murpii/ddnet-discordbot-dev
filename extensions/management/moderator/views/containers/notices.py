import discord

from utils.text import to_discord_timestamp
from utils.containers import ALERT_ACCENT
from extensions.management.moderator.views.spam_actions import SpamModButton, SpamDealtButton


class GhostPingView(discord.ui.LayoutView):
    """Public ghost-ping notice, these happen a lot for some reason"""

    def __init__(self, author: discord.abc.User, content: str, *, edited: bool = False):
        super().__init__(timeout=None)

        title = "## Ghost ping detected!" + (" (edit)" if edited else "")
        # body = discord.utils.escape_mentions(content[:1024]) if content else "*No content*"

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"{title}\n"
                        f"Author: {author.mention}"
                    ),
                    discord.ui.TextDisplay(
                        f"Content:\n"
                        f">>> {content}"
                    ),
                    accessory=discord.ui.Thumbnail(author.display_avatar.url),
                ),
                accent_colour=ALERT_ACCENT,
            )
        )


class SpamAlertView(discord.ui.LayoutView):
    def __init__(
            self,
            role_id: int,
            user: discord.abc.User,
            channel_ids,
            content: str,
            action: str,
            deleted: int = 0,
            files: list[discord.File] | None = None,
    ):
        super().__init__(timeout=None)

        channels = ", ".join(f"<#{cid}>" for cid in channel_ids)
        message_text = (
            discord.utils.escape_mentions(content[:1024]) if content else "*no text content*"
        )

        header = (
            f"## ⚔️ Spam Alert\n"
            f"<@&{role_id}>\n"
            f"{user.mention} tripped the spam filter.\n"
        )
        details = (
            f"**Spammed in:** {channels}\n"
            f"**Action:** {action}\n"
            f"**Removed:** {deleted} message{'' if deleted == 1 else 's'}\n"
            f"**Message**:\n"
            f">>> {message_text}"
        )
        footer = (
            f"-# Author ID: {user.id} | {to_discord_timestamp(discord.utils.utcnow(), 'f')}"
        )

        items = [
            discord.ui.Section(
                discord.ui.TextDisplay(header),
                accessory=discord.ui.Thumbnail(user.display_avatar.url),
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),  # noqa
            discord.ui.TextDisplay(details),
        ]

        if files:
            items.append(
                discord.ui.MediaGallery(
                    *(discord.MediaGalleryItem(f"attachment://{f.filename}") for f in files)
                )
            )

        items.append(discord.ui.Separator())
        items.append(
            discord.ui.ActionRow(
                SpamModButton("info", user.id),
                SpamModButton("kick", user.id),
                SpamModButton("ban", user.id),
                SpamDealtButton(),
            )
        )
        items.append(discord.ui.Separator())
        items.append(discord.ui.TextDisplay(footer))

        self.add_item(
            discord.ui.Container(*items, accent_colour=discord.Colour.orange().value)
        )
