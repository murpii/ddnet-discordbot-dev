import discord

from utils.containers import has_embed_blocks, markup_view
from utils.text import resolve_role_mentions, resolve_user_mentions


class EditMsgModal(discord.ui.Modal, title="Edit Message"):
    text = discord.ui.TextInput(
        label="New content",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    def __init__(self, message: discord.Message, markup: str | None = None):
        super().__init__()
        self.message = message
        self.text.default = markup if markup is not None else message.content

    async def on_submit(self, interaction: discord.Interaction):
        content = self.text.value

        # mentions render properly but never notify, discord doesn't send pings for mentions added by an edit
        content = resolve_role_mentions(content, interaction.guild)
        content, _mentioned = resolve_user_mentions(content, interaction.guild)
        allowed = discord.AllowedMentions(roles=False, users=False, everyone=False)

        if self.message.flags.components_v2:
            await self.message.edit(view=markup_view(content), allowed_mentions=allowed)
        elif has_embed_blocks(content):
            # the V2 flag is immutable, a plain message can't gain containers
            await interaction.response.send_message(
                "This is a plain text message, Discord can't add containers to it. "
                "Echo the text as a new message instead.",
                ephemeral=True,
            )
            return
        else:
            await self.message.edit(content=content, allowed_mentions=allowed)

        await interaction.response.send_message("Message updated.", ephemeral=True)
