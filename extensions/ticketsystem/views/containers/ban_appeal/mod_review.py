import discord

from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.text import to_discord_timestamp


class ModReviewContainer(discord.ui.LayoutView):
    """Message posted in the private mod-review thread of a ban-appeal ticket.

    Highlights the moderator(s) who issued the matching ban(s) and asks for proof.
    Other moderators see the thread via the Manage Threads permission, so no role
    ping is needed.
    """

    def __init__(
            self,
            resolved: list[discord.Member],
            unresolved: list[str],
            bans: list[dict],
    ):
        super().__init__(timeout=None)

        intro: list[str] = []
        if resolved:
            intro.append(
                f"{' '.join(m.mention for m in resolved)} -- a ban appeal was opened for an IP **you** banned."
            )
        if unresolved:
            intro.append(
                "Could not match these issuer name(s) to a Discord user: "
                + ", ".join(f"`{n}`" for n in unresolved)
            )
        if not resolved and not unresolved:
            intro.append("No ban issuer could be determined from the synced ban list.")
        intro.append(
            "Please post **all the proof you have** here (demos, data dumps, screenshots, "
            "chat logs) so another moderator can review the case."
        )

        items = [
            discord.ui.TextDisplay("# Moderator Review"),
            large_seperator(),
            discord.ui.TextDisplay("\n\n".join(intro)),
        ]

        if bans:
            ban_lines = []
            for ban in bans:
                expiry = to_discord_timestamp(ban["expires"], style="R") if ban.get("expires") else "unknown"
                ban_lines.append(
                    f"-# `{ban.get('name') or 'Unknown'}` -- {ban.get('reason') or 'no reason'} (expires {expiry})"
                )
            items.append(large_seperator())
            items.append(discord.ui.TextDisplay("**Matching ban(s):**\n" + "\n".join(ban_lines)))

        self.add_item(discord.ui.Container(*items, accent_colour=TICKET_ACCENT))
