import logging
from typing import Optional, Tuple

import discord

from utils.containers import NoticeView, ChannelToolView
from utils.text import parse_message_url, resolve_role_mentions, resolve_user_mentions
from extensions.chat.views.echo_modal import EchoModal

log = logging.getLogger()

MESSAGE_URL_NOTE = 'Right-click the message and use "Copy Message Link". A plain message ID will not work here.'


async def fetch_message_from_url(bot, url: str) -> Tuple[Optional[discord.Message], Optional[str]]:
    parsed = parse_message_url(url)
    if parsed is None:
        return None, f"That doesn't look like a message URL. {MESSAGE_URL_NOTE}"

    _guild_id, channel_id, message_id = parsed

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None, "I can't see the channel that message is in."

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        return None, "No message found under that URL (was it deleted?)."
    except discord.Forbidden:
        return None, "I'm not allowed to read messages in that channel."

    return message, None


class EchoPanel(ChannelToolView):
    title = "Echo a message"
    instructions = "Pick a channel, then compose the message the bot should send there."

    def extra_rows(self) -> list:
        return [discord.ui.ActionRow(ComposeButton())]


class ComposeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Compose", style=discord.ButtonStyle.primary)  # noqa

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await self.view.require_channel(interaction)
        if channel is None:
            return
        # EchoModal is the same modal /echo uses; it sends to the channel
        # and confirms ephemerally on its own.
        await interaction.response.send_modal(EchoModal(channel))


class EditMessageModal(discord.ui.Modal, title="Edit a bot message"):
    url = discord.ui.Label(
        text="Message URL (not the message ID!)",
        description=MESSAGE_URL_NOTE,
        component=discord.ui.TextInput(max_length=200),
    )
    content = discord.ui.Label(
        text="New content",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,  # noqa
            max_length=2000,
        ),
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        message, error = await fetch_message_from_url(self.bot, self.url.component.value)
        if error:
            await interaction.response.send_message(view=NoticeView(error), ephemeral=True)
            return

        if message.author != self.bot.user:
            await interaction.response.send_message(
                view=NoticeView("I can only edit my own messages."), ephemeral=True
            )
            return

        content = resolve_role_mentions(self.content.component.value, interaction.guild)
        content, _mentioned = resolve_user_mentions(content, interaction.guild)

        try:
            await message.edit(
                content=content,
                allowed_mentions=discord.AllowedMentions(roles=False, users=False, everyone=False),
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                view=NoticeView("Editing failed (is that an embed/container message?)."),
                ephemeral=True,
            )
            return

        log.info("ModHub: %s edited message %d", interaction.user, message.id)
        await interaction.response.send_message(
            view=NoticeView(f"Updated [the message]({message.jump_url})."), ephemeral=True
        )


class DeleteMessageModal(discord.ui.Modal, title="Delete a message"):
    url = discord.ui.Label(
        text="Message URL (not the message ID!)",
        description=MESSAGE_URL_NOTE,
        component=discord.ui.TextInput(max_length=200),
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        message, error = await fetch_message_from_url(self.bot, self.url.component.value)
        if error:
            await interaction.response.send_message(view=NoticeView(error), ephemeral=True)
            return

        description = f"the message from {message.author} in {message.channel.mention}"
        try:
            await message.delete()
        except discord.Forbidden:
            await interaction.response.send_message(
                view=NoticeView(f"I'm not allowed to delete {description}."), ephemeral=True
            )
            return

        log.info(
            "ModHub: %s deleted message %d by %s in #%s",
            interaction.user, message.id, message.author, message.channel,
        )
        await interaction.response.send_message(
            view=NoticeView(f"Deleted {description}."), ephemeral=True
        )
