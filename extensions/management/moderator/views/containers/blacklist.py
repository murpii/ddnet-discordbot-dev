import discord

from utils.containers import ALERT_ACCENT
from utils.text import clip, to_discord_timestamp


class BlacklistAlertView(discord.ui.LayoutView):
    def __init__(self, user: discord.abc.User, channel, trigger: str, content: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Blacklist hit\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Channel:** {channel.mention}\n"
                    f"**Trigger:** `{clip(trigger, 60)}`\n"
                    f"**Message:** {discord.utils.escape_mentions(clip(content, 500))}\n"
                    f"-# {to_discord_timestamp(discord.utils.utcnow(), 'f')}"
                ),
                accent_colour=ALERT_ACCENT,
            )
        )
