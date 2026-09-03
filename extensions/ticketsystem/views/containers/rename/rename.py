import discord

from extensions.guides.render import render_guide
from extensions.guides.store import normalize_lang
from extensions.ticketsystem.ticket import Ticket
from extensions.ticketsystem.views.containers.base import TICKET_ACCENT, large_seperator
from utils.containers import NoticeView
from utils.text import slugify2


class RenameContainer(discord.ui.LayoutView):
    def __init__(self, ticket: Ticket | None = None):
        super().__init__(timeout=None)

        btn1 = discord.ui.Button(
            label="📂 Config Directory",
            style=discord.ButtonStyle.secondary,  # noqa
            custom_id="RenameConfigDirBtn",
        )

        greeting = (
            f"Hello {ticket.creator.mention}, thanks for reaching out!"
            if ticket is not None else "Thanks for reaching out!"
        )

        items = [
            discord.ui.TextDisplay(
                "# [Player Rename Request](https://ddnet.org/renames/)\n"
                f"{greeting}"
            ),
            large_seperator(),
            discord.ui.TextDisplay(
                "To transfer your in-game points to a new name, we need a few details first.\n"
                "## Step 1: Past Renames\n"
                "1. Have you ever received a rename before?\n"
                "- If yes, please mention who processed it.\n"
                "## Step 2: Proof of Ownership\n"
                "To verify that you own the points being moved, we require **ONE** of the following:\n"
                "### 1. Demo files\n"
                "- Upload **10-20 of your oldest raw demo files** showing finishes on DDNet.\n"
                "- Upload the files **as-is**. Do not zip, bundle, or modify them.\n"
                "- Ghost files are not accepted.\n"
                "-# Demo files that contain finishes follow this format: `<map>_<time>_<name>.demo`\n\n"
                "All your demo files can be found inside the config directory:\n"
            ),
            discord.ui.ActionRow(btn1),
            discord.ui.TextDisplay(
                "### 2. Staff confirmation\n"
                "- A vouch from a known DDNet staff member confirming your identity."
            ),
        ]

        if ticket is not None and ticket.rename_data:
            old = ticket.rename_data.old_profile
            new = ticket.rename_data.new_profile
            new_extra = (
                f"Last Finish: `{new.latest_finish or 'None'}`\n"
                f"First Finish: `{new.first_finish or 'None'}`"
                if new.points else ""
            )
            items.append(large_seperator())
            items.append(
                discord.ui.TextDisplay(
                    "## Provided Infos\n"
                    f"**[Current Name](https://ddnet.org/players/{slugify2(old.name)})**\n"
                    f"```{old.name}```"
                    f"Points: `{old.points or 0}`\n"
                    f"Last Finish: `{old.latest_finish or 'None'}`\n"
                    f"First Finish: `{old.first_finish or 'None'}`\n\n"
                    f"**[New Name](https://ddnet.org/players/{slugify2(new.name)})**\n"
                    f"```{new.name}```"
                    f"Points: `{new.points or 0}`\n"
                    f"{new_extra}"
                )
            )

        self.add_item(discord.ui.Container(*items, accent_colour=TICKET_ACCENT))
        btn1.callback = self.btn1_callback

    @staticmethod
    async def btn1_callback(interaction: discord.Interaction):
        # Render the config-directory guide in the clicker's Discord language
        # (falls back to English). Source of truth: data/config/guides.json.
        result = render_guide("configdir", normalize_lang(interaction.locale))
        if result is None:
            await interaction.response.send_message(
                view=NoticeView("The config directory guide is currently unavailable."),
                ephemeral=True,
            )
            return
        view, files = result
        kwargs = {"view": view, "ephemeral": True}
        if files:
            kwargs["files"] = files
        await interaction.response.send_message(**kwargs)
