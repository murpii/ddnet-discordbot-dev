import discord
from discord import SeparatorSpacing

from extensions.misc.embeds.configdir import configdir_embed


class RenameContainer(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        btn1 = discord.ui.Button(
            label="📂 Config Directory",
            style=discord.ButtonStyle.secondary,  # noqa
            custom_id="RenameConfigDirBtn",
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay("# [Player Rename Request](https://ddnet.org/renames/)"),
            discord.ui.Separator(spacing=SeparatorSpacing.large, visible=True),  # noqa
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
            accent_colour=2210995,
        )

        self.add_item(container)
        btn1.callback = self.btn1_callback

    @staticmethod
    async def btn1_callback(interaction: discord.Interaction):
        embed, file = configdir_embed()
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
