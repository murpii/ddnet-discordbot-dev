import discord

from utils.text import resolve_role_mentions, resolve_user_mentions


class EchoModal(discord.ui.Modal, title="Echo Message"):
    # select for highlighting mentions
    highlight_select = discord.ui.Label(
        text="Highlight mentions? (Default: False)",
        description="Should roles be highlighted in the message?",
        component=discord.ui.Select(
            placeholder="Select an option...",
            required=False,
            options=[
                discord.SelectOption(label="Yes", value="true"),
                discord.SelectOption(label="No", value="false"),
            ]
        )
    )

    text_input = discord.ui.Label(
        text="Message content",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            required=True,
            max_length=2000
        )
    )

    def __init__(
            self,
            channel: discord.TextChannel,
            target_message: discord.Message | None = None
    ):
        super().__init__()
        self.channel = channel
        self.target_message: discord.Message = target_message

        if self.target_message:
            self.ping_select = discord.ui.Label(
                text="Ping author?",
                component=discord.ui.Select(
                    placeholder="Select an option...",
                    required=False,
                    options=[
                        discord.SelectOption(label="Yes", value="true"),
                        discord.SelectOption(label="No", value="false"),
                    ]
                )
            )
            self.add_item(self.ping_select)

    async def on_submit(self, interaction: discord.Interaction):
        content = self.text_input.component.value
        ping = False

        values = self.highlight_select.component.values
        highlight = values[0] == "true" if values else False

        if self.target_message:
            values = self.ping_select.component.values
            ping = values[0] == "true" if values else False  # default = no ping

        if highlight:
            content = resolve_role_mentions(content, interaction.guild)

        # @username / @nickname turns into a real mention, exactly those
        # members get pinged, anything that isn't a member stays plain text
        content, mentioned_users = resolve_user_mentions(content, interaction.guild)

        await self.channel.send(
            content=content,
            reference=self.target_message,
            mention_author=ping,
            allowed_mentions=discord.AllowedMentions(
                roles=highlight,
                users=mentioned_users,
                everyone=False
            )
        )

        await interaction.response.send_message("Message sent.", ephemeral=True)
