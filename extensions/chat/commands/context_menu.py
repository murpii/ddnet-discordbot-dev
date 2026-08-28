import discord
from discord import app_commands
from discord.ext import commands

from extensions.chat.views.echo_modal import EchoModal
from extensions.chat.views.edit_modal import EditMsgModal
from utils.containers import message_markup

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import DDNet


class ChatCtxMenu(commands.Cog):
    def __init__(self, bot: "DDNet") -> None:
        self.bot = bot

        # echo message context menu
        self.echo_chat_msg = app_commands.ContextMenu(
            name="Echo a message (this channel)",
            callback=self.echo_context,
            type=discord.AppCommandType.message,  # noqa
        )
        self.bot.tree.add_command(self.echo_chat_msg)

        # edit message context menu
        self.edit_chat_msg = app_commands.ContextMenu(
            name="Edit this message",
            callback=self.edit_context,
            type=discord.AppCommandType.message,  # noqa
        )
        self.bot.tree.add_command(self.edit_chat_msg)

        # reply message context menu
        self.reply_chat_msg = app_commands.ContextMenu(
            name="Reply to this message",
            callback=self.reply_context,
            type=discord.AppCommandType.message,  # noqa
        )
        self.bot.tree.add_command(self.reply_chat_msg)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.echo_chat_msg.name,
            type=self.echo_chat_msg.type,
        )
        self.bot.tree.remove_command(
            self.edit_chat_msg.name,
            type=self.edit_chat_msg.type,
        )
        self.bot.tree.remove_command(
            self.reply_chat_msg.name,
            type=self.reply_chat_msg.type,
        )

    @app_commands.default_permissions(administrator=True)
    async def edit_context(self, interaction: discord.Interaction, message: discord.Message):
        if message.author.id != interaction.client.user.id:
            await interaction.response.send_message(
                "You can only edit bot messages.",
                ephemeral=True
            )
            return

        markup = None
        if message.flags.components_v2:
            markup = message_markup(message)
            if markup is None or len(markup) > 2000:
                await interaction.response.send_message(
                    "This message has components the editor can't rebuild "
                    "(buttons, selects or media). Edit it through the feature that owns it.",
                    ephemeral=True,
                )
                return
        await interaction.response.send_modal(EditMsgModal(message, markup))

    @app_commands.default_permissions(administrator=True)
    async def echo_context(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(EchoModal(interaction.channel))

    @app_commands.default_permissions(administrator=True)
    async def reply_context(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(EchoModal(interaction.channel, message))
