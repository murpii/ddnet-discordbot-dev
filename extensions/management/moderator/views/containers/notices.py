import discord

from utils.text import to_discord_timestamp
from utils.containers import ALERT_ACCENT
from extensions.management.moderator.views.spam_actions import SpamModButton


class GhostPingView(discord.ui.LayoutView):
    """Public ghost-ping notice, these happen a lot for some reason"""

    def __init__(self, author: discord.abc.User, content: str, *, edited: bool = False):
        super().__init__(timeout=None)

        title = "## Ghost ping detected!" + (" (edit)" if edited else "")
        body = discord.utils.escape_mentions(content) if content else "*No content*"

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"{title}\n"
                    f"**Author:** {author} (`{author.id}`)\n"
                    f"**Message:** {body}\n"
                    f"-# {to_discord_timestamp(discord.utils.utcnow(), 'f')}"
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
            files: list[discord.File] | None = None,
    ):
        super().__init__(timeout=None)

        channels = ", ".join(f"<#{cid}>" for cid in channel_ids)
        items = [
            discord.ui.TextDisplay(
                f"<@&{role_id}>\n"
                f"## Spam Alert\n"
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Channels:** {channels}\n"
                f"**Message:** {discord.utils.escape_mentions(content[:1024])}\n"
                f"**Action:** {action}\n"
                f"-# {to_discord_timestamp(discord.utils.utcnow(), 'f')}"
            ),
        ]

        if files:
            items.append(
                discord.ui.MediaGallery(
                    *(discord.MediaGalleryItem(f"attachment://{f.filename}") for f in files)
                )
            )

        items.append(
            discord.ui.ActionRow(
                SpamModButton("kick", user.id),
                SpamModButton("ban", user.id),
            )
        )

        self.add_item(
            discord.ui.Container(*items, accent_colour=discord.Colour.orange().value)
        )
