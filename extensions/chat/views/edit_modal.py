import discord

from utils.text import resolve_role_mentions, resolve_user_mentions


class EditMsgModal(discord.ui.Modal, title="Edit Message"):
    text = discord.ui.TextInput(
        label="New content",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        content = self.text.value

        # mentions render properly but never notify, discord doesn't send pings for mentions added by an edit
        content = resolve_role_mentions(content, interaction.guild)
        content, _mentioned = resolve_user_mentions(content, interaction.guild)

        await self.message.edit(
            content=content,
            allowed_mentions=discord.AllowedMentions(
                roles=False,
                users=False,
                everyone=False
            )
        )

        await interaction.response.send_message("Message updated.", ephemeral=True)
